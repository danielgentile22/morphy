"""CLI wrapper for the preprocess framework.

Usage:
  python scripts/preprocess.py                       # normalize all + compose all states with data
  python scripts/preprocess.py --state 37            # normalize all + compose just NC
  python scripts/preprocess.py --source ar_parcels   # re-normalize just one source (no compose)
  python scripts/preprocess.py --normalize-only      # normalize, no compose
  python scripts/preprocess.py --compose-only --state 12   # compose FL (must already be normalized)
  python scripts/preprocess.py --force-rebuild       # ignore manifest, re-normalize everything
  python scripts/preprocess.py --rebuild-manifest    # rewrite preprocess_manifest.json from on-disk files
  python scripts/preprocess.py --app-assets          # write composite/index.json (no recompose)
  python scripts/preprocess.py --owners-index         # write composite/owners_index.json (cross-state Leads)
  python scripts/preprocess.py --tiles               # build parcels.pmtiles for all composed states
  python scripts/preprocess.py --tiles --state 05    # build parcels.pmtiles for one state
  python scripts/preprocess.py --list-views          # show registered Views
  python scripts/preprocess.py --list-joins          # show registered Joins
  python scripts/preprocess.py --list-states         # show states with normalized parcel data
"""

from __future__ import annotations

import argparse
import logging

# Import registry so all @register_normalizer/_join/_view decorators fire.
from preprocess import registry  # noqa: F401
from preprocess.base import all_joins, all_views
from preprocess.geographies import get_state
from preprocess.manifest import PreprocessManifest, rebuild_from_disk
from preprocess.runner import (
    run_all,
    run_compose_all,
    run_compose_one,
    run_normalize_all,
    run_normalize_one,
)


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_summary(outcome) -> None:
    print()
    print("=== preprocess summary ===")
    print(f"  duration: {outcome.duration_seconds:.1f}s")
    print(f"  normalized OK:          {len(outcome.normalized_ok)}")
    print(f"  normalized skipped:     {len(outcome.normalized_skipped)}")
    print(f"  normalized unavailable: {len(outcome.normalized_unavailable)}")
    print(f"  normalized FAILED:      {len(outcome.normalized_failed)}")
    if outcome.normalized_failed:
        for s in outcome.normalized_failed:
            print(f"    ✗ {s}")
    print(
        f"  composed OK:            {len(outcome.composed_ok)}  ({', '.join(outcome.composed_ok)})"
    )
    if outcome.composed_failed:
        print(f"  composed FAILED:        {len(outcome.composed_failed)}")
        for f in outcome.composed_failed:
            print(f"    ✗ state {f}")


def _stream_progress(phase: str, key: str, info: dict) -> None:
    if phase == "normalize_start":
        print(f"  → normalize {key} …", flush=True)
    elif phase == "normalize_ok":
        print(
            f"    ✓ {key}: {info.get('rows', 0):,} rows, {info.get('bytes', 0) / 1_000_000:.1f} MB"
        )
    elif phase == "normalize_fail":
        print(f"    ✗ {key}: {info.get('error', '')}")
    elif phase == "normalize_skip":
        print(f"    · {key}: skipped ({info.get('reason', '')})")
    elif phase == "normalize_unavailable":
        print(f"    – {key}: not installed")
    elif phase == "compose_start":
        print(f"\n  → compose state {key} ({info.get('name', '')}) …", flush=True)
    elif phase == "compose_ok":
        counts = info.get("counts", {})
        print(
            f"    ✓ state {key}: sources={info['sources']} "
            f"joins={info['joins']} views={info['views']} "
            f"counts={counts}"
        )
    elif phase == "compose_fail":
        print(f"    ✗ state {key}: {info.get('error', '')}")
    elif phase == "app_assets":
        print(f"\n  → app assets: wrote {key}.json ({info.get('states', 0)} states)")
    elif phase == "owners_index":
        print(
            f"\n  → owners index: {info.get('owners', 0):,} owners "
            f"({info.get('cross_state', 0)} cross-state)"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preprocess raw data into canonical + composite outputs.",
    )
    parser.add_argument("--state", help="State FIPS to compose (default: all with parcel data)")
    parser.add_argument(
        "--source",
        help=(
            "Re-normalize a single source by id (no compose). Goes through "
            "the manifest like a full run, so the entry stays consistent."
        ),
    )
    parser.add_argument(
        "--normalize-only", action="store_true", help="Run normalize but skip compose"
    )
    parser.add_argument(
        "--compose-only",
        action="store_true",
        help="Skip normalize; compose what's already normalized",
    )
    parser.add_argument(
        "--force-rebuild", action="store_true", help="Re-normalize every source even if unchanged"
    )
    parser.add_argument(
        "--rebuild-manifest",
        action="store_true",
        help=(
            "Rewrite data/processed/preprocess_manifest.json from on-disk "
            "files. Use after out-of-band fixes to clear stale 'failed' entries."
        ),
    )
    parser.add_argument(
        "--app-assets",
        action="store_true",
        help=(
            "Write app-support assets (composite/index.json) without "
            "re-composing, then exit. Also run automatically at the end "
            "of a normal run so the map app never reads a stale index."
        ),
    )
    parser.add_argument(
        "--owners-index",
        action="store_true",
        help=(
            "Write the cross-state owners index (composite/owners_index.json) "
            "from the per-state parcels_attr.parquet, then exit. Run "
            "--app-assets first so the slim attr parquets exist."
        ),
    )
    parser.add_argument(
        "--tiles",
        action="store_true",
        help=(
            "Build parcels.pmtiles for all composed states (or just --state), "
            "then exit. Streams parcels.parquet through tippecanoe."
        ),
    )
    parser.add_argument(
        "--skip-tiles",
        action="store_true",
        help="In a normal run, skip the tile-generation step that follows compose.",
    )
    parser.add_argument("--list-views", action="store_true", help="List registered Views and exit")
    parser.add_argument("--list-joins", action="store_true", help="List registered Joins and exit")
    parser.add_argument(
        "--list-states",
        action="store_true",
        help="List states with normalized parcel data and exit",
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    args = parser.parse_args()

    _setup_logging(args.log_level)

    if args.list_views:
        for v in all_views():
            print(f"  {v.name:38} ← {', '.join(v.inputs):20}  {v.description}")
        return 0

    if args.list_joins:
        for j in all_joins():
            print(f"  {j.name:34} ← {', '.join(j.inputs):28} → adds: {', '.join(j.columns_added)}")
        return 0

    if args.list_states:
        manifest = PreprocessManifest.load()
        states = {}
        for sid, entry in manifest.normalized.items():
            for f in entry.states_covered:
                states.setdefault(f, []).append(sid)
        for fips in sorted(states):
            print(f"  {fips}  ({', '.join(states[fips])})")
        return 0

    if args.rebuild_manifest:
        m = rebuild_from_disk()
        m.save()
        print(
            f"Rebuilt preprocess_manifest.json: "
            f"{len(m.normalized)} normalized, {len(m.composed)} composed."
        )
        return 0

    if args.app_assets:
        from preprocess.app_assets import run_app_assets

        result = run_app_assets()
        print(f"Wrote {result['index_path']}: {result['states']} state(s) indexed.")
        print(
            f"County boundaries: {len(result['county_boundaries_ok'])} built"
            f"{', ' + str(len(result['county_boundaries_failed'])) + ' failed' if result['county_boundaries_failed'] else ''}."
        )
        print(
            f"Facets + slim parquet: {len(result['facets_ok'])} built"
            f"{', ' + str(len(result['facets_failed'])) + ' failed' if result['facets_failed'] else ''}."
        )
        print(f"Combined towers: {result['towers_count']} → {result['towers_path']}.")
        return 0

    if args.owners_index:
        from preprocess.owners_index import run_owners_index

        result = run_owners_index(progress_callback=_stream_progress)
        print(
            f"Wrote {result['index_path']}: {result['owners']} owner(s) indexed "
            f"({result['cross_state_owners']} cross-state) across "
            f"{', '.join(result['states']) or '—'}."
        )
        return 0

    if args.tiles:
        from preprocess.tiles import run_tiles

        result = run_tiles(args.state)
        if result["skipped"]:
            print(result["message"])
            return 1
        print(
            f"Tiles: {len(result['ok'])} built ({', '.join(result['ok']) or '—'}), "
            f"{len(result['failed'])} failed."
        )
        return 0 if not result["failed"] else 1

    manifest = PreprocessManifest.load()

    if args.source:
        status, _ = run_normalize_one(
            args.source,
            manifest,
            force_rebuild=args.force_rebuild,
            progress_callback=_stream_progress,
        )
        manifest.save()
        print(f"\nnormalize {args.source}: {status}")
        return 0 if status in ("ok", "skipped") else 1

    if args.compose_only:
        if args.state:
            res = run_compose_one(
                get_state(args.state),
                manifest,
                progress_callback=_stream_progress,
            )
            return 0 if res else 1
        else:
            results = run_compose_all(
                manifest,
                progress_callback=_stream_progress,
            )
            manifest.save()
            return 0 if all(r is not None for r in results.values()) else 1

    if args.normalize_only:
        statuses = run_normalize_all(
            manifest,
            force_rebuild=args.force_rebuild,
            progress_callback=_stream_progress,
        )
        n_failed = sum(1 for s in statuses.values() if s == "failed")
        return 0 if n_failed == 0 else 1

    outcome = run_all(
        states=[args.state] if args.state else None,
        force_rebuild=args.force_rebuild,
        skip_tiles=args.skip_tiles,
        progress_callback=_stream_progress,
    )
    _print_summary(outcome)
    return 0 if not outcome.normalized_failed and not outcome.composed_failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
