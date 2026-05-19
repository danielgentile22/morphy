"""HIFLD Cellular Towers (GeoJSON) → canonical `tower`.

Currently MANUAL_ONLY in the puller (DHS retired the public layer in 2024).
This Normalizer runs when the user has dropped a HIFLD GeoJSON manually
into data/raw/hifld_towers/current/.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd

from ..base import (
    NormalizeResult,
    Normalizer,
    add_system_columns,
    quality_report,
    register_normalizer,
    write_quality_report,
)
from ..geom import add_point_derivatives
from ..io import dual_write_spatial, write_raw_parquet
from ._helpers import canon_state_fips, safe_str, to_float

log = logging.getLogger("preprocess.hifld_towers")


@register_normalizer
class HifldTowersNormalizer(Normalizer):
    source_id = "hifld_towers"
    canonical_types = ["tower"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        path = self._find_geojson(raw_dir)
        if path is None:
            raise FileNotFoundError(f"hifld_towers: no .geojson under {raw_dir}")
        gdf = gpd.read_file(path)
        log.info("hifld: read %d features from %s", len(gdf), path.name)
        if gdf.crs is None or gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs("EPSG:4326")
        raw_bytes = write_raw_parquet(gdf, out_dir, name="raw.parquet")

        rows = []
        for _, r in gdf.iterrows():
            geom = r.geometry
            lat = geom.y if (geom is not None and not geom.is_empty) else None
            lon = geom.x if (geom is not None and not geom.is_empty) else None
            state_fips = canon_state_fips(r.get("LocState") or r.get("STATE"))
            rows.append({
                "asr_number": safe_str(r.get("TowReg") or r.get("Tower_ID") or r.get("OBJECTID")),
                "owner_name": safe_str(r.get("Licensee") or r.get("Owner")),
                "height_m": (to_float(r.get("AllStruc") or r.get("Height_ft")) or 0) * 0.3048 or None,
                "structure_type": safe_str(r.get("StrucType")),
                "structure_type_desc": safe_str(r.get("StrucType")),
                "status": safe_str(r.get("LicStatus")),
                "status_desc": "Active" if safe_str(r.get("LicStatus")) == "A" else "",
                "is_active": safe_str(r.get("LicStatus")) == "A",
                "date_built": None,
                "date_dismantled": None,
                "street": safe_str(r.get("LocAdd")),
                "city": safe_str(r.get("LocCity")),
                "state": safe_str(r.get("LocState")),
                "zip": None,
                "county_fips": None,
                "state_fips": state_fips,
                "lat": lat,
                "lon": lon,
                "owner_street": None,
                "owner_city": None,
                "owner_state": None,
                "owner_zip": None,
                "owner_phone": None,
                "coordinate_type": None,
                "extras": {"call_sign": r.get("Callsign"), "loc_county": r.get("LocCounty")},
                "_source_row_id": safe_str(r.get("OBJECTID") or r.get("TowReg")),
                "geometry": geom,
            })
        out = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
        out = add_point_derivatives(out)
        out = add_system_columns(out, self.source_id, "tower")

        files, written = dual_write_spatial(out, out_dir, "towers")
        total = raw_bytes + written
        qr = quality_report(self.source_id, {"raw": gdf, "towers": out})
        qr_path = write_quality_report(out_dir, qr)
        return NormalizeResult(
            raw_rows=len(gdf),
            canonical_rows=len(out),
            bytes=total,
            output_files=files + [out_dir / "raw.parquet", qr_path],
            canonical_types_written=["tower"],
            quality_report=qr,
        )

    @staticmethod
    def _find_geojson(raw_dir: Path) -> Optional[Path]:
        if not raw_dir.exists():
            return None
        cand = list(raw_dir.rglob("*.geojson")) + list(raw_dir.rglob("*.json"))
        return cand[0] if cand else None
