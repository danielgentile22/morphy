"""EIA Form 860 (annual Excel bundle) → canonical `solar_facility`.

Reads the '2___Plant_<year>.xlsx' (lat/lon per plant) and joins to
'3_3_Solar_<year>.xlsx' (solar-specific attributes). Other generation
technologies are excluded — this is the solar pipeline; gas/coal/nuclear
have their own sources of truth.
"""

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

log = logging.getLogger("preprocess.eia_860")


@register_normalizer
class Eia860Normalizer(Normalizer):
    source_id = "eia_860"
    canonical_types = ["solar_facility"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        plant_xlsx = self._find_first(raw_dir, "*Plant*.xlsx")
        solar_xlsx = self._find_first(raw_dir, "*Solar*.xlsx")
        if plant_xlsx is None:
            raise FileNotFoundError(f"eia_860: no Plant_*.xlsx under {raw_dir}")

        # 'Plant' header is on row 2 (row index 1)
        plant = pd.read_excel(plant_xlsx, sheet_name=0, header=1, dtype=str)
        log.info("eia_860: read %d plants from %s", len(plant), plant_xlsx.name)
        solar = None
        if solar_xlsx is not None:
            solar = pd.read_excel(solar_xlsx, sheet_name=0, header=1, dtype=str)
            log.info("eia_860: read %d solar generators from %s", len(solar), solar_xlsx.name)

        merged = plant.copy()
        if solar is not None and "Plant Code" in plant.columns and "Plant Code" in solar.columns:
            merged = plant.merge(
                solar[
                    [
                        "Plant Code",
                        "Technology",
                        "Single-Axis Tracking?",
                        "Dual-Axis Tracking?",
                        "Fixed Tilt?",
                        "Tilt Angle",
                        "Nameplate Capacity (MW)",
                    ]
                ].drop_duplicates(subset="Plant Code"),
                on="Plant Code",
                how="left",
                suffixes=("", "_solar"),
            )

        raw_bytes = write_raw_parquet(merged, out_dir, name="raw.parquet")

        rows = []
        for _, r in merged.iterrows():
            lat = to_float(r.get("Latitude"))
            lon = to_float(r.get("Longitude"))
            geom = None
            if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                geom = Point(lon, lat)
            state_fips = canon_state_fips(r.get("State"))
            county_fips = canon_county_fips(r.get("County"), state_fips=state_fips)
            tech = safe_str(r.get("Technology"))
            tracking = "fixed"
            if safe_str(r.get("Single-Axis Tracking?")).upper() == "Y":
                tracking = "1-axis"
            elif safe_str(r.get("Dual-Axis Tracking?")).upper() == "Y":
                tracking = "2-axis"
            rows.append(
                {
                    "facility_id": safe_str(r.get("Plant Code")),
                    "name": safe_str(r.get("Plant Name")),
                    "operator": safe_str(r.get("Utility Name") or r.get("Operator")),
                    "capacity_mw": to_float(r.get("Nameplate Capacity (MW)")),
                    "online_date": None,
                    "retired_date": None,
                    "is_operational": True,
                    "technology": tech,
                    "tracking_type": tracking,
                    "county_fips": county_fips,
                    "state_fips": state_fips,
                    "geometry": geom,
                    "extras": {"utility_id": r.get("Utility ID"), "sector": r.get("Sector Name")},
                    "_source_row_id": safe_str(r.get("Plant Code")),
                }
            )
        gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
        gdf = add_point_derivatives(gdf)
        gdf = add_system_columns(gdf, self.source_id, "solar_facility")

        files, written = dual_write_spatial(gdf, out_dir, "solar_facilities")
        total = raw_bytes + written
        qr = quality_report(self.source_id, {"raw": merged, "solar_facilities": gdf})
        qr_path = write_quality_report(out_dir, qr)
        return NormalizeResult(
            raw_rows=len(merged),
            canonical_rows=len(gdf),
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
