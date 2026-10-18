"""Manual-install engine: place files into current/ + stamp the manifest.

The headless half of the manual/fallback path (PRD #233 slice 3). A UI
(the data TUI) collects the user's file choices and decisions, then
delegates here:

* ``overwrite_conflicts`` — names that an install would overwrite, so a UI
  can ask before proceeding.
* ``install_files`` — copy files (or safely extract ZIPs) into
  ``data/raw/<id>/current/``, producing the same layout the fetch pipeline
  produces.
* ``mark_manual_install`` — stamp the manifest entry as a successful
  manual install and restart the freshness clock.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .base import DataSource
from .manifest import Manifest
from .sources._helpers import safe_extract_zip
from .storage import current_dir


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

    Delegates to :meth:`Manifest.stamp_installed` — the single owner of the
    file-list/bytes derivation + freshness clock (#264) — so a manual
    install and an auto-fetch produce identical entries for identical
    ``current/`` contents. ``local_version`` becomes ``"manual"``; the
    entry's ``remote_version`` is left as the last checked value. Like the
    other ``mark_*`` mutators, does NOT save — the caller decides.
    """
    manifest.stamp_installed(
        source.id,
        local_version="manual",
        remote_version=manifest.entry(source.id).remote_version,
        cadence_days=source.update_cadence_days,
    )
