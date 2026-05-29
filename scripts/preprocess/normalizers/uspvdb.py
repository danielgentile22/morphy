"""USGS USPVDB (shapefile) → canonical `solar_facility` (polygons)."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd

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
            rows.append(
                {
                    "facility_id": safe_str(r.get("p_id") or r.get("case_id")),
                    "name": safe_str(r.get("p_name") or r.get("plant_name")),
                    "operator": safe_str(r.get("p_owner") or r.get("p_oper")),
                    "capacity_mw": to_float(r.get("p_cap_ac") or r.get("p_cap_dc")),
                    "online_date": safe_str(r.get("p_year")),
                    "retired_date": None,
                    "is_operational": True,
                    "technology": safe_str(r.get("p_tech_sec") or r.get("technology")),
                    "tracking_type": safe_str(r.get("p_axis")),
                    "county_fips": county_fips,
                    "state_fips": state_fips,
                    "extras": {
                        "p_eia_id": r.get("p_eia_id"),
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
