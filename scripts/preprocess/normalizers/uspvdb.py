"""USGS USPVDB (shapefile) → canonical `solar_facility` (polygons).

Carries ``eia_id`` — the EIA plant code (the same code space as the
eia_860 normalizer's ``facility_id``) — as a first-class column: it is
the cross-feed key the solar dedup (MACRO-3) matches on (M-f / #210).
USPVDB v4.0 (2026-04) renamed the field ``p_eia_id`` → ``eia_id``; both
spellings are read so an older extract still normalizes.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from ..base import (
    Normalizer,
    NormalizeResult,
    add_system_columns,
    quality_report,
    register_normalizer,
    write_quality_report,
)
from ..geom import add_polygon_derivatives
from ..io import dual_write_spatial, write_raw_parquet
from .fips import canon_county_fips, canon_state_fips
from .pandas_coerce import safe_str, to_float

log = logging.getLogger("preprocess.uspvdb")


def _eia_id_str(v: object) -> str:
    """The EIA plant code as a clean string ('' when absent).

    Arrives int64 from the v4 shapefile but float when the column carries
    nulls — strip the integral ``.0`` so the key matches eia_860's
    ``facility_id`` strings ("2953", never "2953.0")."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _select_capacity(p_cap_ac: object, p_cap_dc: object) -> tuple[float | None, str | None]:
    """USPVDB capacity standardized to the AC rating (E7).

    USPVDB carries both an AC and a DC nameplate rating (they differ ~1.2–1.4×).
    The old ``to_float(p_cap_ac or p_cap_dc)`` silently mixed the two across
    rows; here we prefer AC, fall back to DC only when AC is absent, and return
    which rating was used so the mix is recorded rather than hidden.
    """
    ac = to_float(p_cap_ac)
    if ac is not None:
        return ac, "AC"
    dc = to_float(p_cap_dc)
    if dc is not None:
        return dc, "DC"
    return None, None


@register_normalizer
class UspvdbNormalizer(Normalizer):
    source_id = "uspvdb"
    canonical_types = ["solar_facility"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        shp = self._find_first(raw_dir, "*.shp")
        if shp is None:
            raise FileNotFoundError(f"uspvdb: no .shp under {raw_dir}")
        gdf = gpd.read_file(shp)
        log.info("uspvdb: %d features from %s", len(gdf), shp.name)
        if gdf.crs is None or gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs("EPSG:4326")
        raw_bytes = write_raw_parquet(gdf, out_dir, name="raw.parquet")

        rows = []
        for _, r in gdf.iterrows():
            state_fips = canon_state_fips(r.get("p_state"))
            county_fips = canon_county_fips(r.get("p_county"), state_fips=state_fips)
            capacity_mw, capacity_rating = _select_capacity(r.get("p_cap_ac"), r.get("p_cap_dc"))
            # v4 name first, pre-v4 fallback (M-f / #210) — see module docstring.
            eia_id = _eia_id_str(r.get("eia_id")) or _eia_id_str(r.get("p_eia_id"))
            rows.append(
                {
                    "facility_id": safe_str(r.get("p_id") or r.get("case_id")),
                    # The EIA plant code — the MACRO-3 dedup key against the
                    # EIA-860/860M feeds (their facility_id is this code).
                    "eia_id": eia_id,
                    "name": safe_str(r.get("p_name") or r.get("plant_name")),
                    "operator": safe_str(r.get("p_owner") or r.get("p_oper")),
                    "capacity_mw": capacity_mw,
                    "online_date": safe_str(r.get("p_year")),
                    "retired_date": None,
                    "is_operational": True,
                    "technology": safe_str(r.get("p_tech_sec") or r.get("technology")),
                    "tracking_type": safe_str(r.get("p_axis")),
                    "county_fips": county_fips,
                    "state_fips": state_fips,
                    "extras": {
                        "capacity_rating": capacity_rating,
                        "p_lulc_pre": r.get("p_lulc_pre"),
                        "p_area": r.get("p_area"),
                    },
                    "_source_row_id": safe_str(r.get("p_id") or r.get("case_id")),
                    "geometry": r.geometry,
                }
            )
        out = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
        out = add_polygon_derivatives(out)
        out = add_system_columns(out, self.source_id, "solar_facility")
        files, written = dual_write_spatial(
            out, out_dir, "solar_facilities", write_simplified_geojson=True
        )
        total = raw_bytes + written
        qr = quality_report(self.source_id, {"raw": gdf, "solar_facilities": out})
        qr_path = write_quality_report(out_dir, qr)
        return NormalizeResult(
            raw_rows=len(gdf),
            canonical_rows=len(out),
            bytes=total,
            output_files=files + [out_dir / "raw.parquet", qr_path],
            canonical_types_written=["solar_facility"],
            quality_report=qr,
        )

    @staticmethod
    def _find_first(raw_dir: Path, pattern: str) -> Path | None:
        if not raw_dir.exists():
            return None
        cand = sorted(raw_dir.rglob(pattern))
        return cand[0] if cand else None
