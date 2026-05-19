"""Verify what is actually present under data/raw/<source_id>/current/.

Each source has a signature describing what its current/ directory should
look like — required filenames or extensions, distinguishing markers,
and (where helpful) a content sniff. Run from CLI or call ``verify_all()``
from the puller UI to surface mismatches before preprocessing.

Reliability note: file-name signatures beat parsing record contents,
since column layouts differ between license/application/lease/transfer
versions of files even when they share table names.

Usage:
    python scripts/verify_raw.py           # CLI report
    from verify_raw import verify_all      # in-process
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fetch import RAW_ROOT
from fetch.registry import all_sources

# Signature schema (every key optional unless noted):
#   label           — human description
#   required        — exact filenames that MUST be present
#   nice_to_have    — filenames that SHOULD be present (informational only)
#   must_not_have   — filenames that, if present, indicate wrong data here
#   required_exts   — at least one file with each extension (lowercase, with dot)
#   shapefile       — True ⇒ require .shp + .shx + .dbf (treated as a unit)
#   content_signature — (filename_glob, substring) — open first matching file
#                       and verify substring appears in first 2 KB
#   min_total_bytes — folder bytes must be ≥ this (catches truncated downloads)
SIGNATURES: dict[str, dict] = {
    # ── Towers ────────────────────────────────────────────────────────────
    "fcc_asr": {
        "label": "FCC ASR — Registrations + FAA Determinations",
        "required": {"RA.dat"},
        "nice_to_have": {"RE.dat", "CO.dat", "EN.dat", "DE.dat", "DP.dat", "DR.dat"},
        "min_total_bytes": 5_000_000,
    },
    "fcc_uls_cellular": {
        "label": "FCC ULS — Cellular (Part 22) Licenses",
        "required": {"HD.dat", "EN.dat", "LO.dat"},
        "nice_to_have": {"FR.dat", "AN.dat", "MK.dat", "CP.dat"},
        "must_not_have": {"_O.dat", "TA.dat", "LD.dat"},
        "min_total_bytes": 5_000_000,
    },
    "fcc_uls_market": {
        "label": "FCC ULS — Market-Based Services Licenses",
        "required": {"HD.dat", "MK.dat"},
        "nice_to_have": {"MC.dat", "MF.dat", "MP.dat", "EM.dat", "EN.dat", "FR.dat"},
        "must_not_have": {"_O.dat", "TA.dat", "LD.dat"},
        "min_total_bytes": 5_000_000,
    },
    "fcc_uls_micro": {
        "label": "FCC ULS — Microwave (Parts 74/101) Licenses",
        "required": {"HD.dat", "EN.dat", "LO.dat", "FR.dat"},
        "nice_to_have": {"BC.dat", "BF.dat", "F2.dat", "FF.dat", "AS.dat", "PA.dat"},
        "must_not_have": {"_O.dat", "TA.dat", "LD.dat"},
        "min_total_bytes": 5_000_000,
    },
    "fcc_uls_ownership": {
        "label": "FCC ULS — Ownership (Form 602) Filings",
        "required": {"_H.dat", "_O.dat"},
        "nice_to_have": {"_A.dat", "_D.dat", "_F.dat", "_T.dat"},
        "min_total_bytes": 100_000,
    },
    "fcc_uls_transfers": {
        "label": "FCC ULS — Assignments & Transfers of Control",
        "required": {"HD.dat", "AT.dat"},
        "nice_to_have": {"TA.dat", "AD.dat", "BD.dat", "CD.dat", "CF.dat"},
        "must_not_have": {"_O.dat", "LD.dat", "RA.dat"},
        "min_total_bytes": 1_000_000,
    },
    "fcc_uls_leasing": {
        "label": "FCC ULS — Spectrum Leasing (Form 608)",
        "required": {"HD.dat", "LD.dat"},
        "nice_to_have": {"LC.dat", "L2.dat", "A2.dat", "AT.dat"},
        "must_not_have": {"_O.dat", "RA.dat"},
        "min_total_bytes": 1_000_000,
    },
    "faa_oeaaa": {
        "label": "FAA Digital Obstacle File",
        # FAA ships DOF.DAT (fixed-width) plus a README. Names sometimes
        # uppercased, sometimes mixed.
        "required_exts": [".dat"],
        "min_total_bytes": 1_000_000,
    },
    "hifld_towers": {
        "label": "HIFLD Cellular Towers (GeoJSON)",
        "required_exts": [".geojson"],
        "content_signature": ("*.geojson", '"FeatureCollection"'),
        "min_total_bytes": 100_000,
    },
    # ── Solar ─────────────────────────────────────────────────────────────
    "eia_860": {
        "label": "EIA Form 860 Excel bundle",
        # Annual release; many .xlsx workbooks
        "required_exts": [".xlsx"],
        "min_total_bytes": 1_000_000,
    },
    "eia_860m": {
        "label": "EIA Form 860M (monthly snapshot)",
        "required_exts": [".xlsx"],
        "min_total_bytes": 100_000,
    },
    "uspvdb": {
        "label": "USGS USPVDB (solar facility polygons)",
        # USGS publishes formats as separate small zips; .shp is canonical
        "required_exts": [".shp", ".csv", ".geojson"],
        "any_ext_ok": True,
        "nice_to_have_exts": [".dbf", ".shx", ".prj"],
        "min_total_bytes": 500_000,
    },
    "lbnl_tts": {
        "label": "LBNL U.S. Distributed Solar & Storage Data (csv or zip)",
        # Either the ~1.9 GB CSV or the ~218 MB zip; both count.
        "required_exts": [".csv", ".zip"],
        "any_ext_ok": True,
        "min_total_bytes": 100_000_000,
    },
    # ── Billboards ────────────────────────────────────────────────────────
    "fdot_billboards": {
        "label": "FDOT Outdoor Advertising permits (Excel)",
        "required_exts": [".xlsx"],
        "min_total_bytes": 500_000,
    },
    "ncdot_billboards": {
        "label": "NCDOT Outdoor Advertising permits (manual)",
        "required_exts": [".xlsx", ".csv", ".xls", ".pdf"],
        "any_ext_ok": True,
        "min_total_bytes": 1_000,
    },
    "txdot_billboards": {
        "label": "TxDOT Outdoor Advertising permits (manual)",
        "required_exts": [".xlsx", ".csv", ".xls", ".pdf"],
        "any_ext_ok": True,
        "min_total_bytes": 1_000,
    },
    # ── Parcels ───────────────────────────────────────────────────────────
    "nc_onemap_parcels": {
        "label": "NC OneMap statewide parcels (shapefile or .gdb)",
        # Modern downloads come as a shapefile zip
        "required_exts": [".shp", ".gdb", ".gpkg"],
        "any_ext_ok": True,
        "nice_to_have_exts": [".dbf", ".shx", ".prj"],
        "min_total_bytes": 500_000_000,
    },
    "fl_fgdl_parcels": {
        "label": "Florida FGDL DSL parcel composite",
        "required_exts": [".shp", ".gdb", ".gpkg"],
        "any_ext_ok": True,
        # ~173 MB zip → bigger when unzipped; threshold leaves a small floor
        # so a truncated download still trips the check.
        "min_total_bytes": 100_000_000,
    },
    "mt_cadastral_parcels": {
        "label": "Montana Cadastral parcels",
        "required_exts": [".shp", ".gdb", ".gpkg"],
        "any_ext_ok": True,
        "min_total_bytes": 100_000_000,
    },
    "mn_parcels": {
        "label": "Minnesota statewide parcels (one or more chunks)",
        # Hennepin alone often forces a multi-chunk download. Accept any
        # geometric format; chunks can be mixed (e.g. one .gdb + several
        # .geojson files in the same current/ folder).
        "required_exts": [".shp", ".gdb", ".gpkg", ".geojson"],
        "any_ext_ok": True,
        "min_total_bytes": 100_000_000,
    },
    "in_parcels": {
        "label": "Indiana statewide parcels",
        "required_exts": [".shp", ".gdb", ".gpkg"],
        "any_ext_ok": True,
        "min_total_bytes": 200_000_000,
    },
    "ar_parcels": {
        "label": "Arkansas statewide parcels",
        "required_exts": [".shp", ".gdb", ".gpkg"],
        "any_ext_ok": True,
        "min_total_bytes": 100_000_000,
    },
    "ut_parcels": {
        "label": "Utah AGRC LIR parcels",
        "required_exts": [".shp", ".gdb", ".gpkg"],
        "any_ext_ok": True,
        "min_total_bytes": 100_000_000,
    },
    "regrid_parcels": {
        "label": "Regrid nationwide parcels (licensed)",
        # Any of the formats Regrid offers
        "required_exts": [".gpkg", ".shp", ".geojson", ".csv", ".parquet"],
        "any_ext_ok": True,
        "min_total_bytes": 100_000_000,
    },
    # ── Distress ──────────────────────────────────────────────────────────
    "hud_oz": {
        "label": "HUD Opportunity Zones (GeoJSON)",
        "required_exts": [".geojson"],
        "content_signature": ("*.geojson", '"FeatureCollection"'),
        "min_total_bytes": 500_000,
    },
    "hud_qct": {
        "label": "HUD Qualified Census Tracts (GeoJSON)",
        "required_exts": [".geojson"],
        "content_signature": ("*.geojson", '"FeatureCollection"'),
        "min_total_bytes": 500_000,
    },
    "arc_distressed": {
        "label": "ARC County Economic Status (Excel)",
        "required_exts": [".xlsx"],
        "min_total_bytes": 100_000,
    },
    "usda_persistent_poverty": {
        "label": "USDA ERS County Typology Codes (CSV)",
        "required_exts": [".csv"],
        "content_signature": ("*.csv", "FIPS"),
        "min_total_bytes": 100_000,
    },
}


@dataclass
class VerifyResult:
    source_id: str
    verdict: str  # 'OK', 'FAIL', 'EMPTY', 'NOT_INSTALLED', 'UNKNOWN'
    nbytes: int
    detail: str
    label: str | None = None


def _human_bytes(n: int) -> str:
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:,.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:,.1f} PB"


def _list_files(folder: Path) -> list[Path]:
    return [p for p in folder.rglob("*") if p.is_file() and not p.is_symlink()]


def _check_content(folder: Path, glob: str, must_contain: str) -> str | None:
    """Return error string if no file in folder matches glob or content missing."""
    matches = list(folder.rglob(glob))
    if not matches:
        return f"no file matching {glob} found"
    try:
        with open(matches[0], encoding="utf-8", errors="replace") as f:
            head = f.read(4096)
    except OSError as e:
        return f"could not read {matches[0].name}: {e}"
    if must_contain not in head:
        return f"{matches[0].name} did not contain expected marker {must_contain!r}"
    return None


def verify_one(source_id: str) -> VerifyResult:
    folder = RAW_ROOT / source_id / "current"
    sig = SIGNATURES.get(source_id)
    label = sig["label"] if sig else None

    if not folder.exists():
        return VerifyResult(source_id, "NOT_INSTALLED", 0, "folder does not exist", label)

    files = _list_files(folder)
    nbytes = sum(f.stat().st_size for f in files)
    if not files:
        return VerifyResult(source_id, "EMPTY", 0, "folder exists but no files", label)

    if not sig:
        return VerifyResult(
            source_id,
            "UNKNOWN",
            nbytes,
            f"{len(files)} file(s) — no signature configured",
            label,
        )

    fail_reasons: list[str] = []

    filenames = {p.name for p in files}
    extensions = {p.suffix.lower() for p in files if p.suffix}
    # Geodatabase / GeoPackage / SQLite "files" are actually directories.
    # Add their suffixes via the directory tree so signature checks work.
    for d in folder.rglob("*"):
        if d.is_dir() and d.suffix.lower() in (".gdb", ".gpkg"):
            extensions.add(d.suffix.lower())

    required = sig.get("required", set())
    missing_required = required - filenames
    if missing_required:
        fail_reasons.append(f"missing required tables: {sorted(missing_required)}")

    must_not_have = sig.get("must_not_have", set())
    foreign = must_not_have & filenames
    if foreign:
        fail_reasons.append(f"contains files that don't belong here: {sorted(foreign)}")

    required_exts = sig.get("required_exts", [])
    if required_exts:
        if sig.get("any_ext_ok"):
            if not any(ext in extensions for ext in required_exts):
                fail_reasons.append(f"no file with any of these extensions: {required_exts}")
        else:
            missing_exts = [e for e in required_exts if e not in extensions]
            if missing_exts:
                fail_reasons.append(f"missing file(s) with extension(s): {missing_exts}")

    content_sig = sig.get("content_signature")
    if content_sig:
        glob, marker = content_sig
        err = _check_content(folder, glob, marker)
        if err:
            fail_reasons.append(err)

    min_bytes = sig.get("min_total_bytes")
    if min_bytes and nbytes < min_bytes:
        fail_reasons.append(
            f"only {_human_bytes(nbytes)} on disk (expected ≥ {_human_bytes(min_bytes)} — likely truncated)"
        )

    if fail_reasons:
        return VerifyResult(source_id, "FAIL", nbytes, "; ".join(fail_reasons), label)

    nice = sig.get("nice_to_have", set())
    have_nice = nice & filenames
    detail_parts = []
    if required:
        detail_parts.append(f"required ✓ ({len(required)})")
    if nice:
        detail_parts.append(f"nice-to-have {len(have_nice)}/{len(nice)}")
    if required_exts:
        detail_parts.append(f"ext ✓ {[e for e in required_exts if e in extensions]}")
    return VerifyResult(
        source_id,
        "OK",
        nbytes,
        ", ".join(detail_parts) if detail_parts else f"{len(files)} file(s)",
        label,
    )


def verify_all() -> list[VerifyResult]:
    return [verify_one(s.id) for s in all_sources()]


# ── CLI ──────────────────────────────────────────────────────────────────


def main() -> int:
    results = verify_all()
    name_w = max(len(r.source_id) for r in results)
    print(f"{'SOURCE':<{name_w}}  {'STATUS':<14}  {'SIZE':>10}  CONTENT")
    print("─" * (name_w + 95))
    n_fail = n_ok = n_missing = n_unknown = 0
    for r in results:
        marker = {
            "OK": "✓",
            "FAIL": "✗",
            "EMPTY": "✗",
            "NOT_INSTALLED": " ",
            "UNKNOWN": "?",
        }.get(r.verdict, "?")
        size = _human_bytes(r.nbytes) if r.nbytes else "—"
        print(f"{r.source_id:<{name_w}}  {marker} {r.verdict:<12}  {size:>10}  {r.detail}")
        if r.verdict in ("FAIL", "EMPTY"):
            n_fail += 1
            if r.label:
                print(f"{'':<{name_w}}                 expected: {r.label}")
        elif r.verdict == "OK":
            n_ok += 1
        elif r.verdict == "NOT_INSTALLED":
            n_missing += 1
        else:
            n_unknown += 1
    print()
    print(f"summary: {n_ok} OK · {n_fail} FAIL · {n_missing} not installed · {n_unknown} unknown")
    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
