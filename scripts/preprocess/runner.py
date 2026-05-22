"""Top-level orchestration used by both the CLI and the UI worker.

Functions:
  - run_normalize_all(...)  — normalize every available source
  - run_normalize_one(...)  — normalize one source by id
  - run_compose_all(...)    — compose every state that has parcel data
  - run_compose_one(...)    — compose one state by FIPS
  - run_all(...)            — normalize all → compose all states

All accept an optional progress_callback to report status as they go.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import NORMALIZED_ROOT, RAW_ROOT
from .base import (
    ComposeResult,
    NormalizeResult,
    all_normalizers,
    get_normalizer,
)
from .compose import ComposeConfig, compose
from .geographies import StateGeography, get_state
from .manifest import PreprocessManifest, get_raw_local_version

log = logging.getLogger("preprocess.runner")


ProgressCallback = Callable[[str, str, dict], None]
# signature: (phase, source_or_state, status_dict)
# phase ∈ {'normalize_start', 'normalize_ok', 'normalize_fail',
#          'normalize_skip', 'normalize_unavailable',
#          'compose_start', 'compose_ok', 'compose_fail', 'compose_skip',
#          'app_assets', 'all_done'}


@dataclass
class RunOutcome:
    normalized_ok: list[str] = field(default_factory=list)
    normalized_failed: list[str] = field(default_factory=list)
    normalized_skipped: list[str] = field(default_factory=list)
    normalized_unavailable: list[str] = field(default_factory=list)
    composed_ok: list[str] = field(default_factory=list)
    composed_failed: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


def run_normalize_one(
    source_id: str,
    manifest: PreprocessManifest,
    *,
    force_rebuild: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> tuple[str, NormalizeResult | None]:
    """Normalize a single source. Returns (status, result_or_None).

    Status one of 'ok', 'failed', 'skipped', 'unavailable'.
    """
    n = get_normalizer(source_id)
    raw_dir = RAW_ROOT / source_id / "current"
    out_dir = NORMALIZED_ROOT / source_id

    if not n.is_available(raw_dir):
        _emit(progress_callback, "normalize_unavailable", source_id, {"reason": "no raw data"})
        return "unavailable", None

    raw_lv = get_raw_local_version(source_id)
    if not force_rebuild and manifest.is_normalize_fresh(
        source_id,
        raw_local_version=raw_lv,
        out_dir=out_dir,
    ):
        _emit(progress_callback, "normalize_skip", source_id, {"reason": "unchanged"})
        return "skipped", None

    _emit(progress_callback, "normalize_start", source_id, {})
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        result = n.normalize(raw_dir, out_dir)
    except Exception as e:
        tb = traceback.format_exc(limit=3)
        log.error("normalize %s failed: %s\n%s", source_id, e, tb)
        manifest.record_normalize(
            source_id,
            raw_local_version=raw_lv,
            raw_rows=0,
            canonical_rows=0,
            bytes_written=0,
            canonical_types=n.canonical_types,
            status="failed",
            error=f"{type(e).__name__}: {e}",
        )
        _emit(progress_callback, "normalize_fail", source_id, {"error": str(e)})
        return "failed", None

    states_covered = list(result.quality_report.get("states_covered") or [])
    if not states_covered:
        states_covered = _infer_states_covered(out_dir)
    manifest.record_normalize(
        source_id,
        raw_local_version=raw_lv,
        raw_rows=result.raw_rows,
        canonical_rows=result.canonical_rows,
        bytes_written=result.bytes,
        canonical_types=result.canonical_types_written,
        states_covered=states_covered,
        quality_report_path=str(out_dir / "quality_report.json"),
        status="ok",
    )
    _emit(
        progress_callback,
        "normalize_ok",
        source_id,
        {
            "rows": result.canonical_rows,
            "bytes": result.bytes,
        },
    )
    return "ok", result


def run_normalize_all(
    manifest: PreprocessManifest,
    *,
    force_rebuild: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, str]:
    """Normalize every registered source. Returns {source_id: status}."""
    statuses: dict[str, str] = {}
    for n in all_normalizers():
        status, _ = run_normalize_one(
            n.source_id,
            manifest,
            force_rebuild=force_rebuild,
            progress_callback=progress_callback,
        )
        statuses[n.source_id] = status
    manifest.save()
    return statuses


def run_compose_one(
    state: StateGeography,
    manifest: PreprocessManifest,
    *,
    force_rebuild: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> ComposeResult | None:
    _emit(progress_callback, "compose_start", state.fips, {"name": state.name})
    try:
        cfg = ComposeConfig(state=state, force_rebuild=force_rebuild)
        result = compose(cfg)
    except Exception as e:
        tb = traceback.format_exc(limit=3)
        log.error("compose %s failed: %s\n%s", state.fips, e, tb)
        manifest.record_compose(
            state.fips,
            sources_used=[],
            joins_applied=[],
            views_built=[],
            counts={},
            status="failed",
            error=f"{type(e).__name__}: {e}",
        )
        _emit(progress_callback, "compose_fail", state.fips, {"error": str(e)})
        return None

    manifest.record_compose(
        state.fips,
        sources_used=result.sources_used,
        joins_applied=result.joins_applied,
        views_built=result.views_built,
        counts=result.counts,
        status="ok",
    )
    _emit(
        progress_callback,
        "compose_ok",
        state.fips,
        {
            "sources": len(result.sources_used),
            "joins": len(result.joins_applied),
            "views": len(result.views_built),
            "counts": result.counts,
        },
    )
    return result


def run_compose_all(
    manifest: PreprocessManifest,
    *,
    states: list[StateGeography] | None = None,
    force_rebuild: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, ComposeResult | None]:
    if states is None:
        states = _states_with_normalized_parcel_data(manifest)
    results: dict[str, ComposeResult | None] = {}
    for s in states:
        results[s.fips] = run_compose_one(
            s,
            manifest,
            force_rebuild=force_rebuild,
            progress_callback=progress_callback,
        )
    manifest.save()
    return results


def run_all(
    *,
    state_fips: str | None = None,
    force_rebuild: bool = False,
    skip_tiles: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> RunOutcome:
    """Normalize all sources, then compose either one state or all that have data."""
    import time

    t0 = time.monotonic()
    outcome = RunOutcome()
    manifest = PreprocessManifest.load()

    normalize_statuses = run_normalize_all(
        manifest,
        force_rebuild=force_rebuild,
        progress_callback=progress_callback,
    )
    for sid, st in normalize_statuses.items():
        if st == "ok":
            outcome.normalized_ok.append(sid)
        elif st == "failed":
            outcome.normalized_failed.append(sid)
        elif st == "skipped":
            outcome.normalized_skipped.append(sid)
        else:
            outcome.normalized_unavailable.append(sid)

    if state_fips:
        states = [get_state(state_fips)]
    else:
        states = _states_with_normalized_parcel_data(manifest)

    compose_results = run_compose_all(
        manifest,
        states=states,
        force_rebuild=force_rebuild,
        progress_callback=progress_callback,
    )
    for fips, res in compose_results.items():
        if res is None:
            outcome.composed_failed.append(fips)
        else:
            outcome.composed_ok.append(fips)

    # App-support assets (composite/index.json) — refresh the global
    # state index so the map app never reads a stale state list after a
    # normal run. Auxiliary: a failure here is logged, not fatal — the
    # compose outputs are already on disk and `--app-assets` re-runs it.
    try:
        from .app_assets import run_app_assets

        run_app_assets(progress_callback=progress_callback)
    except Exception as exc:  # noqa: BLE001 — auxiliary step must not abort the run
        log.warning("app-assets step failed; composite/index.json not refreshed: %s", exc)

    # Parcel vector tiles (composite/<fips>/parcels.pmtiles) for every
    # state just composed. Auxiliary + heavy: a missing tippecanoe or a
    # per-state failure is logged, never fatal. Skipped by --skip-tiles.
    if not skip_tiles and outcome.composed_ok:
        from .tiles import build_state_tiles, tippecanoe_available

        if not tippecanoe_available():
            log.warning(
                "tippecanoe not installed — skipping parcels.pmtiles "
                "(brew install tippecanoe; or pass --skip-tiles)"
            )
        else:
            for fips in sorted(set(outcome.composed_ok)):
                try:
                    build_state_tiles(fips)
                except Exception as exc:  # noqa: BLE001 — auxiliary, per-state
                    log.warning("tile generation failed for state %s: %s", fips, exc)

    outcome.duration_seconds = time.monotonic() - t0
    _emit(
        progress_callback,
        "all_done",
        "",
        {
            "duration": outcome.duration_seconds,
            "normalized_ok": len(outcome.normalized_ok),
            "composed_ok": len(outcome.composed_ok),
        },
    )
    return outcome


def _states_with_normalized_parcel_data(manifest: PreprocessManifest) -> list[StateGeography]:
    """States for which at least one parcel Normalizer succeeded."""
    parcel_sources = {n.source_id for n in all_normalizers() if "parcel" in n.canonical_types}
    seen: set[str] = set()
    for sid, entry in (manifest.normalized or {}).items():
        if sid not in parcel_sources:
            continue
        if (entry or {}).get("status") != "ok":
            continue
        for f in entry.get("states_covered") or []:
            seen.add(f)
    if not seen:
        # Fallback: if no parcel data normalized yet, compose for every state
        # that's covered by tower / distress data so the user gets *something*.
        log.info("no normalized parcel data — composing for every state with any normalized data")
        for _sid, entry in (manifest.normalized or {}).items():
            for f in (entry or {}).get("states_covered") or []:
                seen.add(f)
    return [get_state(f) for f in sorted(seen) if f]


def _infer_states_covered(out_dir: Path) -> list[str]:
    """Read every Parquet in out_dir, collect distinct state_fips values."""
    states: set[str] = set()
    try:
        import pandas as pd  # noqa: WPS433

        for p in out_dir.glob("*.parquet"):
            if p.name == "raw.parquet":
                continue
            try:
                df = pd.read_parquet(p, columns=["state_fips"])
            except Exception:
                continue
            for v in df["state_fips"].dropna().unique():
                s = str(v).strip()
                if s:
                    states.add(s)
    except Exception as e:
        log.debug("could not infer states from %s: %s", out_dir, e)
    return sorted(states)


def _emit(cb: ProgressCallback | None, phase: str, key: str, info: dict) -> None:
    if cb is None:
        return
    try:
        cb(phase, key, info)
    except Exception as e:
        log.warning("progress callback raised: %s", e)
