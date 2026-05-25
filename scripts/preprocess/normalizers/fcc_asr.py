"""FCC ASR (Antenna Structure Registration) → canonical `tower` table.

Reads pipe-delimited .dat files from r_tower/ (registrations) and
optionally d_tower/ (FAA determinations). Joins RA + CO + EN by
registration_number, converts DMS to decimal, normalizes status, and
stamps system columns.

Preserves ALL rows (not just constructed) per v3 principle #12 — adds an
is_active flag instead of filtering. Future analyses can query expired/
dismantled towers.
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
from .fcc_dat import dms_to_decimal, read_pipe_dat
from .fips import canon_county_fips, state_fips_from_county_fips
from .pandas_coerce import safe_get, to_float

log = logging.getLogger("preprocess.fcc_asr")

# Field layouts from asr_sql_table_definitions_3.txt
RA_COLS = [
    "record_type",
    "content_indicator",
    "file_number",
    "registration_number",
    "unique_system_identifier",
    "application_purpose",
    "previous_purpose",
    "input_source_code",
    "status_code",
    "date_entered",
    "date_received",
    "date_issued",
    "date_constructed",
    "date_dismantled",
    "date_action",
    "archive_flag_code",
    "version",
    "signature_first_name",
    "signature_middle_initial",
    "signature_last_name",
    "signature_suffix",
    "signature_title",
    "invalid_signature",
    "structure_street_address",
    "structure_city",
    "structure_state_code",
    "county_code",
    "zip_code",
    "height_of_structure",
    "ground_elevation",
    "overall_height_above_ground",
    "overall_height_amsl",
    "structure_type",
    "date_faa_determination_issued",
    "faa_study_number",
    "faa_circular_number",
    "specification_option",
    "painting_and_lighting",
    "mark_light_code",
    "mark_light_other",
    "faa_emi_flag",
    "nepa_flag",
    "date_signed",
    "signature_last_or",
    "signature_first_or",
    "signature_mi_or",
    "signature_suffix_or",
    "title_signed_or",
    "date_signed_or",
]
CO_COLS = [
    "record_type",
    "content_indicator",
    "file_number",
    "registration_number",
    "unique_system_identifier",
    "coordinate_type",
    "latitude_degrees",
    "latitude_minutes",
    "latitude_seconds",
    "latitude_direction",
    "latitude_total_seconds",
    "longitude_degrees",
    "longitude_minutes",
    "longitude_seconds",
    "longitude_direction",
    "longitude_total_seconds",
    "array_tower_position",
    "array_total_tower",
]
EN_COLS = [
    "record_type",
    "content_indicator",
    "file_number",
    "registration_number",
    "unique_system_identifier",
    "entity_type",
    "entity_type_code",
    "entity_type_other",
    "licensee_id",
    "entity_name",
    "first_name",
    "mi",
    "last_name",
    "suffix",
    "phone",
    "fax",
    "internet_address",
    "street_address",
    "street_address2",
    "po_box",
    "city",
    "state",
    "zip_code",
    "attention",
    "frn",
]

# Status code → descriptive label and an is_active flag. Codes per the
# FCC ASR public-access definitions (pubacc_asr_codes_data_elem). The
# live bulk file uses C/G/A/I/T; X/D/R/N are kept for completeness.
STATUS_DESC = {
    "C": ("Constructed", True),
    "G": ("Granted, not constructed", True),
    "A": ("Canceled", False),
    "I": ("Dismantled", False),
    "T": ("Terminated", False),
    "X": ("Cancelled", False),
    "D": ("Dismantled", False),
    "R": ("Rejected", False),
    "N": ("Pending", True),
}

# Structure-type code → label (small reference table).
STRUCTURE_TYPE_DESC = {
    "B": "Building",
    "BANT": "Building with Antenna",
    "BMAST": "Building with Mast",
    "BPIPE": "Building with Pipe",
    "BPOLE": "Building with Pole",
    "BRIDG": "Bridge",
    "BTWR": "Building with Tower",
    "GTOWER": "Guyed Tower",
    "LTOWER": "Lattice Tower",
    "MAST": "Mast",
    "MTOWER": "Monopole Tower",
    "NNGTANN": "Guyed Tower (Non-Lighted)",
    "PIPE": "Pipe",
    "POLE": "Pole",
    "RIG": "Drilling Rig",
    "SIGN": "Sign",
    "SILO": "Silo",
    "STACK": "Stack/Chimney",
    "TANK": "Tank",
    "TOWER": "Tower",
    "UPOLE": "Utility Pole",
    "WTWR": "Water Tower",
}


def _parse_date(s) -> str | None:
    """ASR date format is MM/DD/YYYY. Return ISO YYYY-MM-DD or None."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = str(s).strip()
    if not s:
        return None
    try:
        m, d, y = s.split("/")
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except (ValueError, AttributeError):
        return s  # leave as-is rather than dropping data


@register_normalizer
class FccAsrNormalizer(Normalizer):
    source_id = "fcc_asr"
    canonical_types = ["tower"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        out_dir.mkdir(parents=True, exist_ok=True)

        # ── Locate the per-zip subfolders (r_tower / d_tower) ──────────
        # The puller's fcc_asr.py extracts to current/r_tower/ and current/d_tower/.
        r_dir = self._find_subdir(raw_dir, "r_tower")
        if r_dir is None:
            raise FileNotFoundError(f"FCC ASR r_tower/ folder not found under {raw_dir}")

        ra = read_pipe_dat(r_dir / "RA.dat", RA_COLS, "RA")
        co = read_pipe_dat(r_dir / "CO.dat", CO_COLS, "CO")
        en = read_pipe_dat(r_dir / "EN.dat", EN_COLS, "EN")
        log.info("fcc_asr: RA=%d, CO=%d, EN=%d rows", len(ra), len(co), len(en))

        # ── Coordinates: prefer T (tower), fall back to A (array) ──────
        co_t = co[co["coordinate_type"] == "T"].copy()
        co_a = co[co["coordinate_type"] == "A"].copy()
        have_t = set(co_t["registration_number"])
        co_fallback = co_a[~co_a["registration_number"].isin(have_t)]
        co_use = pd.concat([co_t, co_fallback], ignore_index=True)
        co_use = co_use.drop_duplicates(subset="registration_number", keep="first")
        co_use["lat"] = co_use.apply(
            lambda r: dms_to_decimal(
                r["latitude_degrees"],
                r["latitude_minutes"],
                r["latitude_seconds"],
                r["latitude_direction"],
            ),
            axis=1,
        )
        co_use["lon"] = co_use.apply(
            lambda r: dms_to_decimal(
                r["longitude_degrees"],
                r["longitude_minutes"],
                r["longitude_seconds"],
                r["longitude_direction"],
            ),
            axis=1,
        )

        # ── Owner from EN (entity_type 'O' = Owner) ────────────────────
        owners = en[en["entity_type"] == "O"].copy()
        owners = owners.drop_duplicates(subset="registration_number", keep="first")

        # ── Merge RA + CO + EN ─────────────────────────────────────────
        merged = ra.merge(
            co_use[["registration_number", "lat", "lon", "coordinate_type"]],
            on="registration_number",
            how="left",
        )
        merged = merged.merge(
            owners[
                [
                    "registration_number",
                    "entity_name",
                    "street_address",
                    "city",
                    "state",
                    "zip_code",
                    "phone",
                ]
            ].rename(
                columns={
                    "entity_name": "owner_name",
                    "street_address": "owner_street",
                    "city": "owner_city",
                    "state": "owner_state",
                    "zip_code": "owner_zip",
                    "phone": "owner_phone",
                }
            ),
            on="registration_number",
            how="left",
        )

        # Stage A: full-fidelity raw — every column preserved, no filter.
        raw_bytes = write_raw_parquet(merged, out_dir, name="raw.parquet")

        # ── Build canonical tower rows ────────────────────────────────
        rows: list[dict] = []
        coord_errors = 0
        states_covered: set[str] = set()
        for _, r in merged.iterrows():
            status = safe_get(r, "status_code")
            status_label, is_active = STATUS_DESC.get(status, (status, False))
            structure_type = safe_get(r, "structure_type")
            county_fips = canon_county_fips(
                r.get("county_code"),
                state_fips=safe_get(r, "structure_state_code") or None,
            )
            state_fips = state_fips_from_county_fips(county_fips)
            if state_fips:
                states_covered.add(state_fips)
            lat = to_float(r.get("lat"))
            lon = to_float(r.get("lon"))
            if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                coord_errors += 1
                geometry = None
            else:
                geometry = Point(lon, lat)

            rows.append(
                {
                    "asr_number": safe_get(r, "registration_number"),
                    "owner_name": safe_get(r, "owner_name"),
                    "height_m": to_float(r.get("overall_height_above_ground")),
                    "structure_type": structure_type,
                    "structure_type_desc": STRUCTURE_TYPE_DESC.get(structure_type, structure_type),
                    "status": status,
                    "status_desc": status_label,
                    "is_active": is_active,
                    "date_built": _parse_date(r.get("date_constructed")),
                    "date_dismantled": _parse_date(r.get("date_dismantled")),
                    "street": safe_get(r, "structure_street_address"),
                    "city": safe_get(r, "structure_city"),
                    "state": safe_get(r, "structure_state_code"),
                    "zip": safe_get(r, "zip_code"),
                    "county_fips": county_fips,
                    "state_fips": state_fips,
                    "lat": lat,
                    "lon": lon,
                    "owner_street": safe_get(r, "owner_street"),
                    "owner_city": safe_get(r, "owner_city"),
                    "owner_state": safe_get(r, "owner_state"),
                    "owner_zip": safe_get(r, "owner_zip"),
                    "owner_phone": safe_get(r, "owner_phone"),
                    "coordinate_type": safe_get(r, "coordinate_type"),
                    "extras": {},
                    "_source_row_id": safe_get(r, "registration_number"),
                    "geometry": geometry,
                }
            )

        gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
        gdf = add_point_derivatives(gdf)
        gdf = add_system_columns(gdf, self.source_id, "tower")

        # ── Write outputs ──────────────────────────────────────────────
        files, written = dual_write_spatial(gdf, out_dir, "towers")
        total_bytes = raw_bytes + written

        # ── Quality report ─────────────────────────────────────────────
        warnings = []
        if coord_errors:
            warnings.append(
                f"{coord_errors} rows had invalid or out-of-range coordinates "
                "and were preserved without geometry"
            )
        qr = quality_report(
            self.source_id,
            {"raw": merged, "towers": gdf},
            warnings=warnings,
        )
        qr_path = write_quality_report(out_dir, qr)

        return NormalizeResult(
            raw_rows=len(merged),
            canonical_rows=len(gdf),
            bytes=total_bytes,
            output_files=files + [out_dir / "raw.parquet", qr_path],
            canonical_types_written=["tower"],
            quality_report=qr,
        )

    def is_available(self, raw_dir: Path) -> bool:
        return self._find_subdir(raw_dir, "r_tower") is not None

    @staticmethod
    def _find_subdir(raw_dir: Path, target_name: str) -> Path | None:
        """Locate r_tower / d_tower folder, however deep the user nested it."""
        if not raw_dir.exists():
            return None
        # Direct child first.
        cand = raw_dir / target_name
        if cand.exists() and (cand / "RA.dat").exists():
            return cand
        if cand.exists() and target_name == "d_tower" and any(cand.glob("D*.dat")):
            return cand
        # Search recursively.
        for d in raw_dir.rglob(target_name):
            if not d.is_dir():
                continue
            if target_name == "r_tower" and (d / "RA.dat").exists():
                return d
            if target_name == "d_tower" and any(d.glob("D*.dat")):
                return d
        return None
