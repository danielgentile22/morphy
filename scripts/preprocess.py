"""CLI wrapper for the preprocess framework.

Usage:
  python scripts/preprocess.py                       # normalize all + compose all states with data
  python scripts/preprocess.py --state 37            # normalize all + compose just NC
  python scripts/preprocess.py --normalize-only      # normalize, no compose
  python scripts/preprocess.py --compose-only --state 12   # compose FL (must already be normalized)
  python scripts/preprocess.py --force-rebuild       # ignore manifest, re-normalize everything
  python scripts/preprocess.py --list-views          # show registered Views
  python scripts/preprocess.py --list-joins          # show registered Joins
  python scripts/preprocess.py --list-states         # show states with normalized parcel data
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Bootstrap: when run as a script (not -m), add scripts/ to sys.path.
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Import registry so all @register_normalizer/_join/_view decorators fire.
from preprocess import registry  # noqa: F401, E402
from preprocess.base import all_joins, all_views  # noqa: E402
from preprocess.geographies import get_state  # noqa: E402
from preprocess.manifest import PreprocessManifest  # noqa: E402
from preprocess.runner import (  # noqa: E402
    run_all,
    run_compose_all,
    run_compose_one,
    run_normalize_all,
)


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_summary(outcome) -> None:
    print()
    print(f"=== preprocess summary ===")
    print(f"  duration: {outcome.duration_seconds:.1f}s")
    print(f"  normalized OK:          {len(outcome.normalized_ok)}")
    print(f"  normalized skipped:     {len(outcome.normalized_skipped)}")
    print(f"  normalized unavailable: {len(outcome.normalized_unavailable)}")
    print(f"  normalized FAILED:      {len(outcome.normalized_failed)}")
    if outcome.normalized_failed:
        for s in outcome.normalized_failed:
            print(f"    ✗ {s}")
    print(f"  composed OK:            {len(outcome.composed_ok)}  ({', '.join(outcome.composed_ok)})")
    if outcome.composed_failed:
        print(f"  composed FAILED:        {len(outcome.composed_failed)}")
        for f in outcome.composed_failed:
            print(f"    ✗ state {f}")


def _stream_progress(phase: str, key: str, info: dict) -> None:
    if phase == "normalize_start":
        print(f"  → normalize {key} …", flush=True)
    elif phase == "normalize_ok":
        print(f"    ✓ {key}: {info.get('rows', 0):,} rows, "
              f"{info.get('bytes', 0)/1_000_000:.1f} MB")
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
        print(f"    ✓ state {key}: sources={info['sources']} "
              f"joins={info['joins']} views={info['views']} "
              f"counts={counts}")
    elif phase == "compose_fail":
        print(f"    ✗ state {key}: {info.get('error', '')}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preprocess raw data into canonical + composite outputs.",
    )
    parser.add_argument("--state", help="State FIPS to compose (default: all with parcel data)")
    parser.add_argument("--normalize-only", action="store_true",
                        help="Run normalize but skip compose")
    parser.add_argument("--compose-only", action="store_true",
                        help="Skip normalize; compose what's already normalized")
    parser.add_argument("--force-rebuild", action="store_true",
                        help="Re-normalize every source even if unchanged")
    parser.add_argument("--list-views", action="store_true",
                        help="List registered Views and exit")
    parser.add_argument("--list-joins", action="store_true",
                        help="List registered Joins and exit")
    parser.add_argument("--list-states", action="store_true",
                        help="List states with normalized parcel data and exit")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
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
        for sid, entry in (manifest.normalized or {}).items():
            for f in (entry or {}).get("states_covered") or []:
                states.setdefault(f, []).append(sid)
        for fips in sorted(states):
            print(f"  {fips}  ({', '.join(states[fips])})")
        return 0

    manifest = PreprocessManifest.load()

    if args.compose_only:
        if args.state:
            res = run_compose_one(
                get_state(args.state), manifest,
                force_rebuild=args.force_rebuild,
                progress_callback=_stream_progress,
            )
            return 0 if res else 1
        else:
            results = run_compose_all(
                manifest, force_rebuild=args.force_rebuild,
                progress_callback=_stream_progress,
            )
            manifest.save()
            return 0 if all(r is not None for r in results.values()) else 1

    if args.normalize_only:
        statuses = run_normalize_all(
            manifest, force_rebuild=args.force_rebuild,
            progress_callback=_stream_progress,
        )
        n_failed = sum(1 for s in statuses.values() if s == "failed")
        return 0 if n_failed == 0 else 1

    outcome = run_all(
        state_fips=args.state,
        force_rebuild=args.force_rebuild,
        progress_callback=_stream_progress,
    )
    _print_summary(outcome)
    return 0 if not outcome.normalized_failed and not outcome.composed_failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
