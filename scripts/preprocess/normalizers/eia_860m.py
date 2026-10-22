"""EIA Form 860M (monthly Excel) → canonical `solar_facility`."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from ..base import (
    Normalizer,
    NormalizeResult,
    add_system_columns,
    quality_report,
    register_normalizer,
    write_quality_report,
)
from ..geom import add_point_derivatives
from ..io import dual_write_spatial, write_raw_parquet
from .fips import canon_county_fips, canon_state_fips
from .pandas_coerce import safe_str, to_float

log = logging.getLogger("preprocess.eia_860m")


@register_normalizer
class Eia860MNormalizer(Normalizer):
    source_id = "eia_860m"
    canonical_types = ["solar_facility"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        xlsx = self._find_xlsx(raw_dir)
        if xlsx is None:
            raise FileNotFoundError(f"eia_860m: no .xlsx under {raw_dir}")

        # Try sheets: 'Operating' first, fall back to 'Operable' / first sheet.
        sheet = None
        for s in ("Operating", "Operable"):
            try:
                pd.read_excel(xlsx, sheet_name=s, nrows=1)
                sheet = s
                break
            except Exception:
                continue
        df = pd.read_excel(xlsx, sheet_name=sheet or 0, header=2, dtype=str)
        # Filter to solar PV / solar thermal
        if "Technology" in df.columns:
            df = df[df["Technology"].astype(str).str.contains("Solar", na=False)].copy()
        log.info("eia_860m: %d solar rows from %s", len(df), xlsx.name)

        raw_bytes = write_raw_parquet(df, out_dir, name="raw.parquet")

        rows = []
        for _, r in df.iterrows():
            lat = to_float(r.get("Latitude"))
            lon = to_float(r.get("Longitude"))
            geom = None
            if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                geom = Point(lon, lat)
            # E5: the 860M column is "Plant State", not "State" — reading the
            # wrong name nulled state_fips on 100% of rows, dropping the whole
            # feed downstream. Keep "State" as a fallback for older vintages.
            state_fips = canon_state_fips(r.get("Plant State") or r.get("State"))
            county_fips = canon_county_fips(
                r.get("Plant County") or r.get("County"), state_fips=state_fips
            )
            rows.append(
                {
                    "facility_id": safe_str(r.get("Plant ID") or r.get("Plant Code")),
                    "name": safe_str(r.get("Plant Name")),
                    "operator": safe_str(r.get("Utility Name") or r.get("Operator")),
                    "capacity_mw": to_float(r.get("Nameplate Capacity (MW)")),
                    "online_date": safe_str(r.get("Operating Year")),
                    "retired_date": None,
                    "is_operational": True,
                    "technology": safe_str(r.get("Technology")),
                    "tracking_type": None,
                    "county_fips": county_fips,
                    "state_fips": state_fips,
                    "geometry": geom,
                    "extras": {},
                    "_source_row_id": safe_str(r.get("Plant ID") or r.get("Plant Code")),
                }
            )
        gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
        gdf = add_point_derivatives(gdf)
        gdf = add_system_columns(gdf, self.source_id, "solar_facility")

        files, written = dual_write_spatial(gdf, out_dir, "solar_facilities")
        total = raw_bytes + written
        qr = quality_report(self.source_id, {"raw": df, "solar_facilities": gdf})
        qr_path = write_quality_report(out_dir, qr)
        return NormalizeResult(
            raw_rows=len(df),
            canonical_rows=len(gdf),
            bytes=total,
            output_files=files + [out_dir / "raw.parquet", qr_path],
            canonical_types_written=["solar_facility"],
            quality_report=qr,
        )

    @staticmethod
    def _find_xlsx(raw_dir: Path) -> Path | None:
        if not raw_dir.exists():
            return None
        cand = sorted(raw_dir.rglob("[!.]*.xlsx"))
        return cand[0] if cand else None
