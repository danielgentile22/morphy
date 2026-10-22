"""Sync the *served* composite to the Fly volume (PRD #96, ADR-064).

Production deploy mirrors only the files the map app fetches under
``/data/processed/composite/...`` to the volume, excluding the per-county
``parcels/`` compose-inputs (~8.43 GB the app never reads). The exclude/include
contract is owned here, in one place, so a deploy can't accidentally ship the
wrong 8 GB or drop the served ``parcels.pmtiles`` / ``parcels_attr.parquet``
tiles.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Directory names that are compose-inputs, never served to the app. A per-state
# composite holds both ``<fips>/parcels.pmtiles`` (a served file we keep) and a
# ``<fips>/parcels/`` directory of per-county GeoJSON inputs (excluded). The
# contract excludes the *directory*, never the ``parcels.*`` files.
EXCLUDE_DIRNAMES = ("parcels",)

# macOS writes a "._<name>" AppleDouble sidecar beside every file on an exFAT
# drive (the external data drive). They are metadata, never served.
SIDECAR_PREFIX = "._"


def _is_excluded(rel: Path) -> bool:
    """True if ``rel`` lives under an excluded directory (matches the dir name
    as a path component, never a filename like ``parcels.pmtiles``)."""
    return any(part in EXCLUDE_DIRNAMES for part in rel.parts[:-1])


def iter_sync_files(src: Path) -> Iterator[Path]:
    """Yield the paths (relative to ``src``) that the deploy should sync."""
    src = Path(src)
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        if _is_excluded(rel) or rel.name.startswith(SIDECAR_PREFIX):
            continue
        yield rel


def rclone_filters() -> list[str]:
    """rclone filter rules expressing the same exclude contract as
    :func:`iter_sync_files`. The trailing ``/**`` matches only paths *inside* a
    directory of that exact name, so ``parcels.pmtiles`` (a sibling file) is
    never caught — only the ``parcels/`` directory's contents are."""
    return [f"- **/{name}/**" for name in EXCLUDE_DIRNAMES] + [f"- {SIDECAR_PREFIX}*"]


@dataclass(frozen=True)
class SyncResult:
    transferred: int
    deleted: int
    dry_run: bool


def _rclone_bin() -> str:
    return shutil.which("rclone") or "rclone"


def _parse_stats(stderr: str) -> tuple[int, int]:
    """Read rclone's final JSON stats line for the transfer/delete counts."""
    transferred = deleted = 0
    for line in stderr.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        stats = obj.get("stats")
        if isinstance(stats, dict):
            transferred = int(stats.get("transfers", transferred))
            deleted = int(stats.get("deletes", deleted))
    return transferred, deleted


def sync(
    src: str | Path,
    dst: str | Path,
    *,
    dry_run: bool = False,
    delete: bool = True,
    rclone: str | None = None,
) -> SyncResult:
    """Mirror the served composite from ``src`` to ``dst`` via rclone.

    ``src``/``dst`` are rclone paths — local dirs in tests, ``remote:bucket/...``
    in prod. ``delete=True`` (the default) uses ``rclone sync`` so the
    destination becomes an exact mirror (files removed at the source are
    deleted); ``delete=False`` uses ``rclone copy`` (additive). ``dry_run``
    reports what would change without writing.
    """
    rclone = rclone or _rclone_bin()
    cmd = [rclone, "sync" if delete else "copy", str(src), str(dst)]
    for rule in rclone_filters():
        cmd += ["--filter", rule]
    if dry_run:
        cmd.append("--dry-run")
    cmd += ["--use-json-log", "-v"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    transferred, deleted = _parse_stats(proc.stderr)
    return SyncResult(transferred=transferred, deleted=deleted, dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Mirror the served composite to an rclone destination (Fly volume / "
            "R2), excluding the per-county parcels/ compose-inputs the app never "
            "fetches. deploy.sh calls this once per leg (laptop→R2, R2→volume)."
        )
    )
    parser.add_argument(
        "src", help="rclone source (e.g. data/processed/composite or r2:bucket/composite)"
    )
    parser.add_argument(
        "dst", help="rclone destination (e.g. r2:bucket/composite or /data/processed/composite)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would change without writing"
    )
    parser.add_argument(
        "--no-delete",
        dest="delete",
        action="store_false",
        help="additive copy (keep destination files absent at source) instead of mirror",
    )
    args = parser.parse_args(argv)

    result = sync(args.src, args.dst, dry_run=args.dry_run, delete=args.delete)
    verb = "would transfer" if result.dry_run else "transferred"
    print(f"{verb} {result.transferred} file(s); deleted {result.deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
