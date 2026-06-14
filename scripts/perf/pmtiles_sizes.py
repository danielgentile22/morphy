#!/usr/bin/env python3
"""Per-state ``parcels.pmtiles`` on-disk sizes — the filesystem half of the
map-app perf-probe (PRD #163 / #164, category E).

The tile sizes are a build artifact, not a browser metric, so they are measured
straight off disk rather than over HTTP. Catalog-driven: it reads the anchor
state list from ``composite/index.json`` (falling back to scanning the composite
directory) so a newly-composed state appears with no edit here.

Sizes are reported in **MiB** (bytes / 1024²) to match the PRD baseline table
(AR 314 / FL 789 / MT 306 / WV 270 MB = 1,679 MB total, measured 2026-06-13).

Usage::

    python scripts/perf/pmtiles_sizes.py            # human-readable table
    python scripts/perf/pmtiles_sizes.py --json      # machine-readable JSON

Local-only; reports sizes of git-ignored build outputs. No PII, no prod data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# scripts/perf/pmtiles_sizes.py -> repo root is two parents up.
REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSITE = REPO_ROOT / "data" / "processed" / "composite"
MIB = 1024 * 1024


def _state_dirs() -> list[tuple[str, str]]:
    """Return ``(fips, abbr)`` pairs, catalog-driven off index.json when present,
    else by scanning the composite directory for numeric state folders."""
    index = COMPOSITE / "index.json"
    if index.is_file():
        try:
            data = json.loads(index.read_text())
            states = data.get("states", [])
            pairs = [(str(s["fips"]), str(s.get("abbr", s["fips"]))) for s in states]
            if pairs:
                return sorted(pairs)
        except (json.JSONDecodeError, KeyError, OSError):
            pass  # fall through to a directory scan
    pairs = []
    if COMPOSITE.is_dir():
        for child in COMPOSITE.iterdir():
            if child.is_dir() and child.name.isdigit():
                pairs.append((child.name, child.name))
    return sorted(pairs)


def collect() -> dict:
    """Per-state pmtiles sizes plus the total, in bytes and rounded MiB."""
    states = []
    total_bytes = 0
    for fips, abbr in _state_dirs():
        path = COMPOSITE / fips / "parcels.pmtiles"
        if not path.is_file():
            states.append({"fips": fips, "abbr": abbr, "present": False, "bytes": 0, "mib": 0})
            continue
        size = path.stat().st_size
        total_bytes += size
        states.append(
            {
                "fips": fips,
                "abbr": abbr,
                "present": True,
                "bytes": size,
                "mib": round(size / MIB, 1),
            }
        )
    return {
        "composite_root": str(COMPOSITE),
        "states": states,
        "total_bytes": total_bytes,
        "total_mib": round(total_bytes / MIB, 1),
    }


def _print_table(result: dict) -> None:
    print(f"parcels.pmtiles sizes  ({result['composite_root']})")
    print(f"{'state':<8}{'fips':<6}{'MiB':>10}{'bytes':>16}")
    print("-" * 40)
    for s in result["states"]:
        if s["present"]:
            print(f"{s['abbr']:<8}{s['fips']:<6}{s['mib']:>10.1f}{s['bytes']:>16,}")
        else:
            print(f"{s['abbr']:<8}{s['fips']:<6}{'(missing)':>10}{'':>16}")
    print("-" * 40)
    print(f"{'TOTAL':<14}{result['total_mib']:>10.1f}{result['total_bytes']:>16,}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)
    result = collect()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_table(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
