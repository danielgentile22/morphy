"""Manual-install engine: place files into current/ + stamp the manifest.

The headless half of the manual/fallback path (PRD #233 slice 3). Any UI
(Qt puller, data TUI) collects the user's file choices and decisions, then
delegates here:

* ``overwrite_conflicts`` — names that an install would overwrite, so a UI
  can ask before proceeding.
* ``install_files`` — copy files (or safely extract ZIPs) into
  ``data/raw/<id>/current/``, producing the same layout the fetch pipeline
  and the old Qt upload produce.
* ``mark_manual_install`` — stamp the manifest entry as a successful
  manual install and restart the freshness clock.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import RAW_ROOT
from .base import DataSource
from .manifest import Manifest
from .sources._helpers import safe_extract_zip
from .storage import current_dir, directory_bytes


def _split(paths: list[Path]) -> tuple[list[Path], list[Path]]:
    zips = [p for p in paths if p.suffix.lower() == ".zip"]
    return zips, [p for p in paths if p.suffix.lower() != ".zip"]


def overwrite_conflicts(
    source_id: str, paths: list[Path], *, extract_zips: bool = True
) -> list[str]:
    """Names in current/ that ``install_files`` would overwrite.

    Extracted-ZIP contents aren't predicted — ``safe_extract_zip``
    silently overwrites, matching the fetch pipeline's behavior.
    """
    cur = current_dir(source_id)
    zips, non_zips = _split(paths)
    candidates = non_zips if extract_zips else non_zips + zips
    return [p.name for p in candidates if (cur / p.name).exists()]


def install_files(
    source_id: str, paths: list[Path], *, extract_zips: bool = True
) -> tuple[int, int, list[str]]:
    """Copy/extract ``paths`` into current/. Returns (copied, extracted, errors).

    ZIPs extract into a same-named subfolder so multi-zip sources like
    fcc_asr land in current/r_tower/ + current/d_tower/ (matching the
    fetch pipeline's layout). Parcel sources' normalizers use rglob, so
    subfolders are harmless there.
    """
    cur = current_dir(source_id)
    cur.mkdir(parents=True, exist_ok=True)
    zips, non_zips = _split(paths)

    copied = 0
    extracted = 0
    errors: list[str] = []

    for src in non_zips:
        try:
            shutil.copy2(src, cur / src.name)
            copied += 1
        except OSError as e:
            errors.append(f"{src.name}: {type(e).__name__}: {e}")

    for zp in zips:
        try:
            if extract_zips:
                sub = cur / zp.stem
                sub.mkdir(parents=True, exist_ok=True)
                extracted += len(safe_extract_zip(zp, sub))
            else:
                shutil.copy2(zp, cur / zp.name)
                copied += 1
        except Exception as e:  # noqa: BLE001 — bad zip, unsafe path, OSError
            errors.append(f"{zp.name}: {type(e).__name__}: {e}")

    return (copied, extracted, errors)


def mark_manual_install(source: DataSource, manifest: Manifest) -> None:
    """Stamp the manifest entry to reflect a successful manual install.

    Resets ``status`` to ``"ok"``, clears any prior ``fetch_failed`` /
    ``check_failed`` error, refreshes the file list and byte count from
    disk, and recomputes ``next_recommended_check_at`` from the source's
    declared cadence. Like the other ``mark_*`` mutators, does NOT save
    the manifest — the caller decides persistence.
    """
    cur = current_dir(source.id)
    files = [p for p in cur.rglob("*") if p.is_file() and not p.is_symlink()]
    entry = manifest.entry(source.id)
    now = datetime.now(UTC)
    entry.local_version = "manual"
    entry.status = "ok"
    entry.bytes = directory_bytes(cur)
    rels = []
    for p in files:
        try:
            rels.append(str(p.relative_to(RAW_ROOT)))
        except ValueError:
            rels.append(str(p))
    entry.files = rels
    entry.error = None
    entry.fetched_at = now.isoformat(timespec="seconds")
    entry.checked_at = entry.fetched_at
    cadence = source.update_cadence_days
    entry.update_cadence_days = cadence
    if cadence is not None:
        entry.next_recommended_check_at = (now + timedelta(days=cadence)).isoformat(
            timespec="seconds"
        )
    else:
        entry.next_recommended_check_at = None
