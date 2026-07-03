"""FCC ULS (Universal Licensing System) → canonical `license` / `location`
rows, for the Phase 1 carrier-identification bands.

The ``entity`` layer was dropped (audit M-e / #220): it was composed but
consumed by nothing, and the only thing it carried — the licensee name + FRN —
the ``license`` layer already merges from EN ``entity_type 'L'``.

Slice A (#12) revives the ULS normalize layer that ADR-013 deferred, scoped
to the four bands carriers actually use on cell towers — Cellular (Part 22),
Broadband PCS (Part 24), AWS (Part 27) and 700 MHz (Part 27). See ADR-053 §A.

**On-disk reality vs the issue's assumption.** The issue (and an older cut of
DATA_SOURCES.md) assumed four separate raw directories — `fcc_uls_cellular`,
`fcc_uls_pcs`, `fcc_uls_aws`, `fcc_uls_700mhz`. The FCC does *not* ship them
that way. There are only two relevant bulk files:

* ``l_cell``   (``data/raw/fcc_uls_cellular/current/``) — Part 22 site-based
  Cellular, a single radio service (``CL``).
* ``l_market`` (``data/raw/fcc_uls_market/current/``)   — the *Market-Based
  Services* bundle: PCS, AWS, 700 MHz, **plus** WCS, 600 MHz, Narrowband PCS,
  paging, BRS/EBS and ~30 other geographic-area services, all interleaved in
  one table set and distinguished only by the HD ``radio_service_code``.

So "the four Phase 1 bands" in practice = all of ``l_cell`` + the PCS / AWS /
700 MHz **radio-service-code subset** of ``l_market``. Every other market
service (notably WCS and Microwave, kept deferred by ADR-013) is excluded by
:data:`MARKET_BANDS`. That band-scope exclusion is the *one* documented
row-dropping exception to the full-fidelity rule (CLAUDE.md §8): we keep every
row of an in-scope license (blank coords, missing asr_number and all) and add
status columns rather than filtering on quality.

**Two normalizers, one module.** ``fcc_uls_cellular`` writes the single
``cellular`` band at its source root; ``fcc_uls_market`` classifies by service
code and writes one ``pcs`` / ``aws`` / ``700mhz`` sub-directory per band. Both
stamp a ``band`` column on every row so the downstream ULS↔ASR join (#24) and
the carrier-brand rollup (#22) never have to care where a row was written.

**Coordinates are unreliable.** Per FCC public-access guidance, ULS LO
coordinates are approximate and frequently blank/zero — use them for
carrier-presence corroboration, not siting. The high-precision join key is
``asr_number`` (the LO tower_registration_number) where present; #11 audits its
coverage and #24 falls back to spatial proximity where it's absent.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ..base import (
    OUTPUT_BASENAMES,
    Normalizer,
    NormalizeResult,
    _read_state_paths,
    add_system_columns,
    quality_report,
    register_normalizer,
    write_quality_report,
)
from ..io import write_parquet, write_raw_parquet
from .fcc_dat import dms_to_decimal, read_pipe_dat
from .fips import canon_state_fips
from .pandas_coerce import safe_str, to_float

log = logging.getLogger("preprocess.fcc_uls")

# ── ULS pipe-delimited record layouts ────────────────────────────────────────
# Field order from the FCC public-access database definitions (v5). Only the
# leading, stable columns are consumed; the long boolean/certification tails
# are named for documentation and so read_pipe_dat's fixed-width contract holds
# (every row in the current extract has exactly these counts: HD=59, EN=30,
# LO=51, FR=30 — verified on disk).
HD_COLS = [
    "record_type",
    "unique_system_identifier",
    "uls_file_number",
    "ebf_number",
    "call_sign",
    "license_status",
    "radio_service_code",
    "grant_date",
    "expired_date",
    "cancellation_date",
    "eligibility_rule_num",
    "applicant_type_code_reserved",
    "alien",
    "alien_government",
    "alien_corporation",
    "alien_officer",
    "alien_control",
    "revoked",
    "convicted",
    "adjudged",
    "involved_reserved",
    "common_carrier",
    "non_common_carrier",
    "private_comm",
    "fixed",
    "mobile",
    "radiolocation",
    "satellite",
    "developmental_sta",
    "interconnected_service",
    "certifier_first_name",
    "certifier_mi",
    "certifier_last_name",
    "certifier_suffix",
    "certifier_title",
    "gender",
    "african_american",
    "native_american",
    "hawaiian",
    "asian",
    "white",
    "hispanic",
    "effective_date",
    "last_action_date",
    "auction_id",
    "reg_stat_broad_serv",
    "band_manager",
    "type_serv_broad_serv",
    "alien_ruling",
    "licensee_name_change",
    "whitespace_ind",
    "additional_cert_choice",
    "additional_cert_answer",
    "discontinuation_ind",
    "regulatory_compliance_ind",
    "eligibility_cert_900",
    "transition_plan_cert_900",
    "return_spectrum_cert_900",
    "payment_cert_900",
]
EN_COLS = [
    "record_type",
    "unique_system_identifier",
    "uls_file_number",
    "ebf_number",
    "call_sign",
    "entity_type",
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
    "city",
    "state",
    "zip_code",
    "po_box",
    "attention_line",
    "sgin",
    "frn",
    "applicant_type_code",
    "applicant_type_other",
    "status_code",
    "status_date",
    "lic_category_code",
    "linked_license_id",
    "linked_callsign",
]
LO_COLS = [
    "record_type",
    "unique_system_identifier",
    "uls_file_number",
    "ebf_number",
    "call_sign",
    "location_action_performed",
    "location_type_code",
    "location_class_code",
    "location_number",
    "site_status",
    "corresponding_fixed_location",
    "location_address",
    "location_city",
    "location_county",
    "location_state",
    "radius_of_operation",
    "area_of_operation_code",
    "clearance_indicator",
    "ground_elevation",
    "lat_degrees",
    "lat_minutes",
    "lat_seconds",
    "lat_direction",
    "long_degrees",
    "long_minutes",
    "long_seconds",
    "long_direction",
    "max_lat_degrees",
    "max_lat_minutes",
    "max_lat_seconds",
    "max_lat_direction",
    "max_long_degrees",
    "max_long_minutes",
    "max_long_seconds",
    "max_long_direction",
    "nepa",
    "quiet_zone_notification_date",
    "tower_registration_number",  # ← the FCC ASR registration number (asr_number)
    "height_of_support_structure",
    "overall_height_of_structure",
    "structure_type",
    "airport_id",
    "location_name",
    "units_hand_held",
    "units_mobile",
    "units_temp_fixed",
    "units_aircraft",
    "units_itinerant",
    "status_code",
    "status_date",
    "earth_station_agreement",
]
FR_COLS = [
    "record_type",
    "unique_system_identifier",
    "uls_file_number",
    "ebf_number",
    "call_sign",
    "frequency_action_performed",
    "location_number",
    "antenna_number",
    "class_station_code",
    "op_altitude_code",
    "frequency_assigned",  # lower edge (MHz)
    "frequency_upper_band",  # upper edge (MHz)
    "frequency_carrier",
    "time_begin_operations",
    "time_end_operations",
    "power_output",
    "power_erp",
    "tolerance",
    "frequency_ind",
    "status",
    "eirp",
    "transmitter_make",
    "transmitter_model",
    "auto_transmitter_power_control",
    "cnt_mobile_units",
    "cnt_mob_pagers",
    "freq_seq_id",
    "status_code",
    "status_date",
    "date_first_used",
]

# ── Radio-service-code → band classification (THE Slice-A scope decision) ─────
# Source: FCC ULS Radio Service Codes reference. Cellular lives in its own bulk
# file (l_cell, all rows ``CL``); the rest are carved out of l_market by code.
# Codes NOT listed here are out of band-scope and dropped: WS (WCS) and the
# Microwave file stay deferred per ADR-013; WT (600 MHz), CN/CY (Narrowband PCS)
# and all paging / BRS-EBS / other market services are simply not one of the
# four Phase-1 bands. WP (700 MHz Upper Block D) is mapped for robustness though
# it has zero rows in the current extract.
MARKET_BANDS: dict[str, set[str]] = {
    "pcs": {"CW"},  # Broadband PCS (Part 24)
    "aws": {"AW", "AT", "AD", "AH"},  # AWS-1 / AWS-3 / AWS-4 / AWS H-Block (Part 27)
    "700mhz": {"WY", "WZ", "WU", "WX", "WP"},  # Lower + Upper + Guard band (Part 27)
}
CELLULAR_BANDS: dict[str, set[str] | None] = {"cellular": None}  # None = take every row

# HD license_status code → human label (FCC public-access definitions).
LICENSE_STATUS_DESC: dict[str, str] = {
    "A": "Active",
    "C": "Cancelled",
    "E": "Expired",
    "L": "Pending Legal Status",
    "P": "Parent Station",
    "T": "Terminated",
    "X": "Term Pending",
}

# License-level columns carried straight from HD.
_LICENSE_HD_COLS = [
    "unique_system_identifier",
    "call_sign",
    "radio_service_code",
    "license_status",
    "grant_date",
    "expired_date",
    "cancellation_date",
    "effective_date",
    "last_action_date",
]


def _parse_date(value) -> str | None:
    """ULS date format is MM/DD/YYYY → ISO YYYY-MM-DD. Blank → None."""
    s = safe_str(value)
    if not s:
        return None
    try:
        m, d, y = s.split("/")
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except (ValueError, AttributeError):
        return s  # leave unparseable values intact rather than dropping data


def _blank_to_none(value) -> str | None:
    s = safe_str(value)
    return s or None


def _validate_coords(lat, lon) -> tuple[float | None, float | None, str]:
    """Classify a (lat, lon) pair → (lat, lon, status).

    status ∈ {"ok", "missing", "out_of_range"}. Out-of-range and null-island
    (0, 0) coordinates are nulled out but the row is preserved.
    """
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        return None, None, "missing"
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None, None, "out_of_range"
    if lat == 0.0 and lon == 0.0:
        return None, None, "missing"
    return lat, lon, "ok"


def _find_dat_dir(raw_dir: Path) -> Path | None:
    """Locate the folder holding the .dat tables (l_cell / l_market), however
    deeply the puller or a manual unzip nested it."""
    if not raw_dir.exists():
        return None
    if (raw_dir / "HD.dat").exists():
        return raw_dir
    for hd in sorted(raw_dir.rglob("HD.dat")):
        if hd.is_file():
            return hd.parent
    return None


def _build_license(
    hd_band: pd.DataFrame, en: pd.DataFrame, fr: pd.DataFrame, band: str
) -> pd.DataFrame:
    """One row per license (HD), enriched with the licensee name/FRN (EN
    entity_type 'L') and the assigned frequency range (FR)."""
    lic = hd_band[_LICENSE_HD_COLS].copy()
    lic = lic.rename(columns={"unique_system_identifier": "usi", "call_sign": "callsign"})
    lic["band"] = band
    lic["license_status_desc"] = lic["license_status"].map(
        lambda s: LICENSE_STATUS_DESC.get(safe_str(s), safe_str(s))
    )
    for col in (
        "grant_date",
        "expired_date",
        "cancellation_date",
        "effective_date",
        "last_action_date",
    ):
        lic[col] = lic[col].map(_parse_date)

    # Licensee (entity_type 'L') name + FRN, one per usi.
    licensee = en[en["entity_type"] == "L"][
        ["unique_system_identifier", "entity_name", "frn"]
    ].drop_duplicates(subset="unique_system_identifier", keep="first")
    licensee = licensee.rename(
        columns={"unique_system_identifier": "usi", "entity_name": "licensee_name"}
    )
    licensee["frn"] = licensee["frn"].map(_blank_to_none)
    licensee["licensee_name"] = licensee["licensee_name"].map(_blank_to_none)
    lic = lic.merge(licensee, on="usi", how="left")

    # Assigned frequency range from FR (corroborates the band classification).
    freq = _frequency_summary(fr, set(hd_band["unique_system_identifier"]))
    lic = lic.merge(freq, on="usi", how="left")

    lic["state_fips"] = None  # licenses are national; tower state lives on `location`
    lic["_source_row_id"] = lic["usi"]
    return lic


def _frequency_summary(fr: pd.DataFrame, usi_set: set[str]) -> pd.DataFrame:
    """Per-license assigned-frequency envelope (low MHz, high MHz) from FR."""
    cols = ["usi", "freq_low_mhz", "freq_high_mhz"]
    if fr.empty:
        return pd.DataFrame(columns=cols)
    sub = fr[fr["unique_system_identifier"].isin(usi_set)].copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    sub["low"] = sub["frequency_assigned"].map(to_float)
    sub["high"] = sub["frequency_upper_band"].map(to_float)
    # An FR row with no explicit upper edge is a single assigned frequency.
    sub["high"] = sub["high"].fillna(sub["low"])
    grouped = sub.groupby("unique_system_identifier").agg(
        freq_low_mhz=("low", "min"), freq_high_mhz=("high", "max")
    )
    grouped = grouped.reset_index().rename(columns={"unique_system_identifier": "usi"})
    return grouped[cols]


def _build_location(lo_band: pd.DataFrame, band: str) -> pd.DataFrame:
    """One row per LO record. Every location is preserved; coordinates are
    DMS→decimal (EPSG:4326) with a coord_status flag, and asr_number is
    surfaced as a first-class column (blank when the LO row carries none)."""
    if lo_band.empty:
        return pd.DataFrame(
            columns=[
                "usi",
                "callsign",
                "band",
                "location_number",
                "location_address",
                "location_city",
                "location_county",
                "location_state",
                "state_fips",
                "lat",
                "lon",
                "coord_status",
                "asr_number",
                "structure_type",
                "ground_elevation_m",
                "support_height_m",
                "overall_height_m",
                "_source_row_id",
            ]
        )
    lo = lo_band.copy()

    def _coords(row):
        lat = dms_to_decimal(
            safe_str(row["lat_degrees"]),
            safe_str(row["lat_minutes"]),
            safe_str(row["lat_seconds"]),
            safe_str(row["lat_direction"]),
        )
        lon = dms_to_decimal(
            safe_str(row["long_degrees"]),
            safe_str(row["long_minutes"]),
            safe_str(row["long_seconds"]),
            safe_str(row["long_direction"]),
        )
        return _validate_coords(lat, lon)

    coords = lo.apply(_coords, axis=1, result_type="expand")
    coords.columns = ["lat", "lon", "coord_status"]

    out = pd.DataFrame(
        {
            "usi": lo["unique_system_identifier"],
            "callsign": lo["call_sign"],
            "band": band,
            "location_number": lo["location_number"].map(safe_str),
            "location_address": lo["location_address"].map(_blank_to_none),
            "location_city": lo["location_city"].map(_blank_to_none),
            "location_county": lo["location_county"].map(_blank_to_none),
            "location_state": lo["location_state"].map(_blank_to_none),
            "lat": coords["lat"],
            "lon": coords["lon"],
            "coord_status": coords["coord_status"],
            "asr_number": lo["tower_registration_number"].map(_blank_to_none),
            "structure_type": lo["structure_type"].map(_blank_to_none),
            "ground_elevation_m": lo["ground_elevation"].map(to_float),
            "support_height_m": lo["height_of_support_structure"].map(to_float),
            "overall_height_m": lo["overall_height_of_structure"].map(to_float),
        }
    )
    out["state_fips"] = out["location_state"].map(canon_state_fips)
    seq = out.groupby(["usi", "location_number"]).cumcount().astype(str)
    out["_source_row_id"] = out["usi"] + "-" + out["location_number"] + "-" + seq
    return out


def _band_extras(band: str, codes, license_df, location_df) -> dict:
    """The per-band quality numbers #11/#24 care about — asr_number coverage
    and usable-coordinate rate — alongside row counts + the service codes that
    landed in this band."""
    n_loc = len(location_df)
    asr_rate = round(float(location_df["asr_number"].notna().mean()), 4) if n_loc else None
    coord_rate = round(float((location_df["coord_status"] == "ok").mean()), 4) if n_loc else None
    return {
        "band": band,
        "service_codes": sorted(codes)
        if codes
        else sorted(set(license_df["radio_service_code"].map(safe_str))),
        "license_count": len(license_df),
        "location_count": n_loc,
        "asr_number_populated_rate": asr_rate,
        "coordinate_usable_rate": coord_rate,
    }


def _band_warnings(extras: dict) -> list[str]:
    asr = extras["asr_number_populated_rate"]
    coord = extras["coordinate_usable_rate"]
    asr_pct = f"{asr * 100:.1f}%" if asr is not None else "n/a"
    coord_pct = f"{coord * 100:.1f}%" if coord is not None else "n/a"
    return [
        "ULS coordinates are approximate per FCC public-access guidance — use "
        f"for carrier-presence corroboration, not siting ({coord_pct} of "
        f"'{extras['band']}' locations carry usable coordinates).",
        f"asr_number (FCC ASR cross-reference key) populated on {asr_pct} of "
        f"'{extras['band']}' locations; the remainder need the spatial-proximity "
        "fallback in the ULS↔ASR join (see #11 / #24).",
    ]


def _write_band(
    band_dir: Path,
    source_id: str,
    band: str,
    license_df: pd.DataFrame,
    location_df: pd.DataFrame,
    hd_band: pd.DataFrame,
) -> tuple[object, list[Path], int]:
    """Stamp system columns, atomically write the two canonical parquets
    (license + location) + a Stage-A raw.parquet + a per-band
    quality_report.json. Returns (quality_report, files, bytes).

    The ``entity`` layer was dropped (audit M-e / #220): it was composed but
    consumed by nothing, and the one thing it carried — the licensee name +
    FRN — the ``license`` layer already merges from EN ``entity_type 'L'``."""
    band_dir.mkdir(parents=True, exist_ok=True)

    license_df = add_system_columns(license_df, source_id, "license")
    location_df = add_system_columns(location_df, source_id, "location")

    files: list[Path] = []
    total = 0
    for name, df in (("license", license_df), ("location", location_df)):
        path = band_dir / f"{name}.parquet"
        total += write_parquet(df, path)
        files.append(path)
    total += write_raw_parquet(hd_band, band_dir, name="raw.parquet")
    files.append(band_dir / "raw.parquet")

    extras = _band_extras(band, MARKET_BANDS.get(band), license_df, location_df)
    qr = quality_report(
        source_id,
        {"license": license_df, "location": location_df},
        warnings=_band_warnings(extras),
    )
    qr.extras.update(extras)
    qr_path = write_quality_report(band_dir, qr)
    files.append(qr_path)

    log.info(
        "fcc_uls[%s]: license=%d location=%d (asr=%s, coords=%s)",
        band,
        extras["license_count"],
        extras["location_count"],
        extras["asr_number_populated_rate"],
        extras["coordinate_usable_rate"],
    )
    return qr, files, total


def _normalize(
    dat_dir: Path,
    out_dir: Path,
    source_id: str,
    band_specs: dict[str, set[str] | None],
    *,
    nest: bool,
) -> NormalizeResult:
    """Shared driver. Reads the five .dat tables once, then for each band
    filters HD by radio-service-code, builds the license/location pair and
    writes it. ``nest`` puts each band in its own sub-directory (the multi-band
    market file); a single-band source writes at the root."""
    out_dir.mkdir(parents=True, exist_ok=True)

    hd = read_pipe_dat(dat_dir / "HD.dat", HD_COLS, "HD")
    en = read_pipe_dat(dat_dir / "EN.dat", EN_COLS, "EN")
    lo = read_pipe_dat(dat_dir / "LO.dat", LO_COLS, "LO")
    fr_path = dat_dir / "FR.dat"
    fr = (
        read_pipe_dat(fr_path, FR_COLS, "FR") if fr_path.exists() else pd.DataFrame(columns=FR_COLS)
    )
    log.info(
        "fcc_uls[%s]: read HD=%d EN=%d LO=%d FR=%d", source_id, len(hd), len(en), len(lo), len(fr)
    )

    files: list[Path] = []
    total_bytes = 0
    raw_rows = 0
    canonical_rows = 0
    band_frames: dict[str, dict[str, pd.DataFrame]] = {}
    band_reports: dict[str, object] = {}
    all_warnings: list[str] = []
    all_extras: dict[str, dict] = {}

    for band, codes in band_specs.items():
        hd_band = hd if codes is None else hd[hd["radio_service_code"].isin(codes)].copy()
        usi_set = set(hd_band["unique_system_identifier"])
        lo_band = lo[lo["unique_system_identifier"].isin(usi_set)]

        license_df = _build_license(hd_band, en, fr, band)
        location_df = _build_location(lo_band, band)

        band_dir = (out_dir / band) if nest else out_dir
        qr, band_files, band_bytes = _write_band(
            band_dir, source_id, band, license_df, location_df, hd_band
        )
        files.extend(band_files)
        total_bytes += band_bytes
        raw_rows += len(hd_band)
        canonical_rows += len(license_df)
        band_frames[band] = {
            "license": license_df,
            "location": location_df,
        }
        band_reports[band] = qr
        all_warnings.extend(qr.warnings)
        all_extras[band] = qr.extras

    # The framework reads <out_dir>/quality_report.json (runner.record_normalize).
    # For a single-band source that file already exists (band_dir == out_dir);
    # for the multi-band market file, write an aggregate alongside the per-band
    # reports so the manifest + offline inspection see every band at a glance.
    if nest:
        agg_tables: dict[str, pd.DataFrame] = {}
        for band, frames in band_frames.items():
            for ct, df in frames.items():
                agg_tables[f"{band}.{ct}"] = df
        agg = quality_report(source_id, agg_tables, warnings=all_warnings)
        agg.extras["bands"] = all_extras
        agg_path = write_quality_report(out_dir, agg)
        if agg_path not in files:
            files.append(agg_path)
        report = agg
    else:
        # Single-band source: its per-band report already lives at out_dir root.
        report = next(iter(band_reports.values()))

    return NormalizeResult(
        raw_rows=raw_rows,
        canonical_rows=canonical_rows,
        bytes=total_bytes,
        output_files=files,
        canonical_types_written=["license", "location"],
        quality_report=report,
    )


@register_normalizer
class FccUlsCellularNormalizer(Normalizer):
    """Part 22 site-based Cellular (l_cell) → the single ``cellular`` band."""

    source_id = "fcc_uls_cellular"
    canonical_types = ["license", "location"]

    def is_available(self, raw_dir: Path) -> bool:
        return _find_dat_dir(raw_dir) is not None

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        dat_dir = _find_dat_dir(raw_dir)
        if dat_dir is None:
            raise FileNotFoundError(f"fcc_uls_cellular: no HD.dat found under {raw_dir}")
        return _normalize(dat_dir, out_dir, self.source_id, CELLULAR_BANDS, nest=False)


@register_normalizer
class FccUlsMarketNormalizer(Normalizer):
    """Market-Based Services (l_market) → the PCS / AWS / 700 MHz subset, one
    band per sub-directory. Every other market radio service is excluded."""

    source_id = "fcc_uls_market"
    canonical_types = ["license", "location"]

    def is_available(self, raw_dir: Path) -> bool:
        return _find_dat_dir(raw_dir) is not None

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        dat_dir = _find_dat_dir(raw_dir)
        if dat_dir is None:
            raise FileNotFoundError(f"fcc_uls_market: no HD.dat found under {raw_dir}")
        return _normalize(dat_dir, out_dir, self.source_id, MARKET_BANDS, nest=True)

    def load_state_data(self, state_fips: str) -> dict:
        """Read the market bands from their per-band sub-dirs.

        THE audit MACRO-1 fix (#220): this source writes each band to a nested
        ``<source>/<band>/<basename>.parquet`` (``pcs/`` / ``aws/`` /
        ``700mhz/``), but the default loader only probes the flat
        ``<source>/<basename>.parquet`` — so compose loaded **zero** market
        locations and every PCS / AWS / 700 MHz carrier (Verizon-market,
        T-Mobile, Dish) silently dropped before the ULS↔ASR join. Here we
        gather each canonical type across all band dirs and filter to the state
        through the shared reader. (Market locations are geographic-area — no
        ``asr_number`` — so they attach via the join's proximity fallback:
        ``likely`` / ``possible``, never ``verified``.)"""
        from .. import NORMALIZED_ROOT

        src_dir = NORMALIZED_ROOT / self.source_id
        if not src_dir.exists():
            return {}
        out: dict = {}
        for ct in self.canonical_types:
            basename = OUTPUT_BASENAMES.get(ct, ct)
            paths = [src_dir / band / f"{basename}.parquet" for band in MARKET_BANDS]
            paths = [p for p in paths if p.exists()]
            if not paths:
                continue
            frame = _read_state_paths(paths, ct, state_fips)
            if frame is not None:
                out[ct] = frame
        return out
