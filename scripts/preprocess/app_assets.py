"""App-support assets — outputs the map app consumes that the composer
itself does not produce.

Phase A: ``composite/index.json`` — the global state list. The map app
reads this one small file to learn which states are composed, instead of
probing 51 FIPS codes for ``catalog.json`` on every load.

Later phases of the app rehaul add more app-support assets here:
``county_boundaries.geojson`` (Phase B) and ``facets.json`` /
``parcels_attr.parquet`` (Phase C). They are all run together by
``run_app_assets()`` so a single ``preprocess.py --app-assets`` (or the
tail of a normal run) keeps every app input fresh without re-composing.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from . import COMPOSITE_ROOT
from .geographies import get_state

# index.json shape version — bump when the structure changes so the app
# can detect a mismatch instead of silently mis-reading an old file.
INDEX_SCHEMA_VERSION = 1

INDEX_FILENAME = "index.json"

# FIPS codes that have a composite/<fips>/ directory on disk but must NOT
# surface in the app. Indiana (18) was dropped from this cut (ADR-017);
# its composite/18/ directory is kept on disk (user decision 2026-05-21,
# the destructive cleanup was declined) and still carries a stale
# pre-ADR-052 catalog.json — without this skip it would appear as a
# third, broken state.
EXCLUDED_FIPS: frozenset[str] = frozenset({"18"})


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def build_index(composite_root: Path | None = None) -> dict:
    """Scan ``composite/*/`` and assemble the global state index.

    A directory counts as a composed state when it contains
    ``catalog.json``. Per-state ``bbox`` / ``abbr`` / ``name`` come from
    ``geographies.get_state()`` — the authoritative per-state envelope
    (rehaul-plan choice 2); ``counts`` come from each ``summary.json``.
    Directories whose FIPS is in ``EXCLUDED_FIPS`` or is not a known
    state are skipped rather than crashing the scan.
    """
    root = composite_root if composite_root is not None else COMPOSITE_ROOT
    states: list[dict] = []
    if root.exists():
        for state_dir in sorted(root.iterdir()):
            if not state_dir.is_dir():
                continue
            fips = state_dir.name
            if fips in EXCLUDED_FIPS:
                continue
            if not (state_dir / "catalog.json").exists():
                continue
            try:
                geo = get_state(fips)
            except KeyError:
                # Directory name is not a recognised FIPS — skip it.
                continue
            states.append(
                {
                    "fips": geo.fips,
                    "abbr": geo.abbr,
                    "name": geo.name,
                    "bbox": list(geo.bbox),
                    "counts": _read_counts(state_dir / "summary.json"),
                }
            )
    states.sort(key=lambda s: s["name"])
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "generated_at": _utcnow_iso(),
        "states": states,
    }


def _read_counts(summary_path: Path) -> dict[str, int]:
    """Return the ``counts`` block from a state's ``summary.json``.

    Missing or corrupt summary.json yields an empty dict — the app shows
    the state with no count badges rather than failing to list it.
    """
    if not summary_path.exists():
        return {}
    try:
        summary = json.loads(summary_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    raw = summary.get("counts")
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items() if isinstance(v, int)}


def write_composite_index(
    composite_root: Path | None = None,
    index_path: Path | None = None,
) -> Path:
    """Build and write ``composite/index.json`` atomically.

    The write goes through a temp file + ``os.replace`` so a reader (the
    app) never sees a half-written index. Returns the path written.
    """
    root = composite_root if composite_root is not None else COMPOSITE_ROOT
    if index_path is None:
        index_path = root / INDEX_FILENAME
    index = build_index(root)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=index_path.parent, prefix=".index.", suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(index, f, indent=2, sort_keys=True)
        os.replace(tmp_path, index_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return index_path


def run_app_assets(progress_callback=None) -> dict:
    """Run every app-support-asset step.

    Phase A: the composite/index.json writer. Phase B adds the per-state
    county_boundaries.geojson (the choropleth source). Phase C adds the
    per-state parcels_attr.parquet + facets.json (the DuckDB-WASM
    inputs). All steps only *read* existing composites — no recompose.

    Returns a small result dict for the CLI to print.
    """
    index_path = write_composite_index()
    index = json.loads(index_path.read_text())
    n_states = len(index.get("states", []))
    if progress_callback:
        progress_callback(
            "app_assets",
            "index",
            {"path": str(index_path), "states": n_states},
        )

    # County choropleth source — built from a vendored Census file +
    # county_scores; auxiliary, so a failure is reported, not raised.
    from .county_boundaries import run_county_boundaries

    cb = run_county_boundaries()

    # DuckDB-WASM inputs — the slim parcels_attr.parquet + facets.json.
    from .facets import run_facets

    fc = run_facets()

    return {
        "index_path": str(index_path),
        "states": n_states,
        "county_boundaries_ok": cb["ok"],
        "county_boundaries_failed": cb["failed"],
        "facets_ok": fc["ok"],
        "facets_failed": fc["failed"],
    }
