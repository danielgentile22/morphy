"""FAA Digital Obstacle File (DOF.DAT, fixed-width) → canonical `tower`.

Column positions per the README inside the FAA archive.
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
from ._helpers import canon_state_fips, safe_str, to_float

log = logging.getLogger("preprocess.faa_dof")

# FAA DOF fixed-width column positions (1-indexed, inclusive — converted below).
# Verified against the live DOF.DAT column layout: every one of the 636k
# data rows parses to a valid lat/lon with these offsets. The previous
# offsets were misaligned (lat/lon bled across field boundaries), which is
# why every FAA tower landed in the composite with null geometry.
_FW_FIELDS = [
    ("oas_code", 1, 2),
    ("obstacle_number", 4, 9),
    ("verification_status", 11, 11),
    ("country", 13, 14),
    ("state", 16, 17),
    ("city", 19, 32),
    ("lat_dms", 36, 47),
    ("lon_dms", 49, 61),
    ("obstacle_type", 63, 80),
    ("quantity", 81, 82),
    ("agl_ft", 84, 88),
    ("amsl_ft", 90, 94),
]


def _dms_to_decimal_packed(s: str) -> float | None:
    """Parse FAA DOF 'DD-MM-SS.SSH' or 'DDD-MM-SS.SSH' → decimal degrees."""
    if not s:
        return None
    s = s.strip()
    if len(s) < 9:
        return None
    try:
        # Last character is the direction.
        direction = s[-1].upper()
        body = s[:-1].strip()
        parts = body.replace("-", " ").split()
        d = float(parts[0])
        m = float(parts[1]) if len(parts) > 1 else 0
        sec = float(parts[2]) if len(parts) > 2 else 0
        val = abs(d) + m / 60.0 + sec / 3600.0
        if direction in ("S", "W"):
            val = -val
        return val
    except (ValueError, IndexError):
        return None


@register_normalizer
class FaaDofNormalizer(Normalizer):
    source_id = "faa_oeaaa"
    canonical_types = ["tower"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        dat = self._find_dat(raw_dir)
        if dat is None:
            raise FileNotFoundError(f"faa_oeaaa: DOF.DAT not found under {raw_dir}")
        rows = self._parse_fixed_width(dat)
        log.info("faa_dof: %d raw rows from %s", len(rows), dat.name)
        raw_df = pd.DataFrame(rows)
        raw_bytes = write_raw_parquet(raw_df, out_dir, name="raw.parquet")

        canonical_rows = []
        coord_errors = 0
        for r in rows:
            lat = _dms_to_decimal_packed(r.get("lat_dms"))
            lon = _dms_to_decimal_packed(r.get("lon_dms"))
            geom = None
            if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                coord_errors += 1
            else:
                geom = Point(lon, lat)
            state_fips = canon_state_fips(r.get("state"))
            canonical_rows.append(
                {
                    "asr_number": r.get("obstacle_number"),  # FAA's own ID, not FCC ASR
                    "owner_name": "",
                    "height_m": (to_float(r.get("agl_ft")) or 0) * 0.3048 or None,
                    "structure_type": safe_str(r.get("obstacle_type")),
                    "structure_type_desc": safe_str(r.get("obstacle_type")),
                    "status": safe_str(r.get("verification_status")),
                    "status_desc": "Verified"
                    if safe_str(r.get("verification_status")) == "V"
                    else "Other",
                    "is_active": True,
                    "date_built": None,
                    "date_dismantled": None,
                    "street": None,
                    "city": safe_str(r.get("city")),
                    "state": safe_str(r.get("state")),
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
                    "extras": {
                        "oas_code": r.get("oas_code"),
                        "amsl_ft": r.get("amsl_ft"),
                        "quantity": r.get("quantity"),
                        "country": r.get("country"),
                    },
                    "_source_row_id": safe_str(r.get("obstacle_number")),
                    "geometry": geom,
                }
            )

        gdf = gpd.GeoDataFrame(canonical_rows, geometry="geometry", crs="EPSG:4326")
        gdf = add_point_derivatives(gdf)
        gdf = add_system_columns(gdf, self.source_id, "tower")

        files, written = dual_write_spatial(gdf, out_dir, "towers")
        total = raw_bytes + written
        warnings = []
        if coord_errors:
            warnings.append(f"{coord_errors} rows had invalid DMS coordinates")
        qr = quality_report(self.source_id, {"raw": raw_df, "towers": gdf}, warnings=warnings)
        qr_path = write_quality_report(out_dir, qr)
        return NormalizeResult(
            raw_rows=len(raw_df),
            canonical_rows=len(gdf),
            bytes=total,
            output_files=files + [out_dir / "raw.parquet", qr_path],
            canonical_types_written=["tower"],
            quality_report=qr,
        )

    @staticmethod
    def _find_dat(raw_dir: Path) -> Path | None:
        if not raw_dir.exists():
            return None
        cand = list(raw_dir.rglob("DOF.DAT")) + list(raw_dir.rglob("DOF.dat"))
        return cand[0] if cand else None

    @staticmethod
    def _parse_fixed_width(path: Path) -> list[dict]:
        out: list[dict] = []
        # Skip the header lines until we hit a data row (state field is alpha).
        with open(path, encoding="latin-1") as f:
            for line in f:
                if len(line) < 100:
                    continue
                row: dict = {}
                for name, start, end in _FW_FIELDS:
                    row[name] = line[start - 1 : end].strip()
                # Skip header / divider rows
                if not row["obstacle_number"].isdigit():
                    continue
                out.append(row)
        return out
