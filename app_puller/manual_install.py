"""Manual-install support: pick-files-and-copy + manifest stamping.

Two related pieces of the same workflow:

* ``pick_and_upload(source, parent)`` opens a file picker and copies (or
  extracts ZIPs) into ``data/raw/<id>/current/``. Used by both the
  details-pane button and the walkthrough modal so the user doesn't
  have to navigate to ``current/`` by hand after a manual download.
* ``mark_manual_install(source, manifest)`` is the side effect: stamps
  the manifest entry as a successful manual install and resets cadence
  bookkeeping so the freshness timer starts now.

ZIP archives are auto-extractable. Overwrites are confirmed once at the
top to keep the flow non-modal-heavy.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fetch import RAW_ROOT
from fetch.base import DataSource
from fetch.manifest import Manifest
from fetch.sources._helpers import safe_extract_zip
from fetch.storage import current_dir, directory_bytes
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget


def pick_and_upload(
    source: DataSource,
    parent: QWidget,
) -> tuple[int, int, list[str]] | None:
    """Open a file picker; copy/extract chosen files into current/.

    Returns ``(n_copied, n_extracted, errors)`` on success.
    Returns ``None`` if the user cancelled the picker.
    """
    start_dir = Path.home() / "Desktop"
    if not start_dir.exists():
        start_dir = Path.home()

    files, _ = QFileDialog.getOpenFileNames(
        parent,
        f"Upload files for {source.name}",
        str(start_dir),
        (
            "All files (*);;ZIP archives (*.zip);;CSV (*.csv);;"
            "Shapefile parts (*.shp *.shx *.dbf *.prj *.cpg);;"
            "GeoJSON (*.geojson *.json)"
        ),
    )
    if not files:
        return None

    return _move_into_current([Path(f) for f in files], source, parent)


def _move_into_current(
    paths: list[Path],
    source: DataSource,
    parent: QWidget,
) -> tuple[int, int, list[str]]:
    cur = current_dir(source.id)
    cur.mkdir(parents=True, exist_ok=True)

    zips = [p for p in paths if p.suffix.lower() == ".zip"]
    non_zips = [p for p in paths if p.suffix.lower() != ".zip"]

    extract_zips = False
    if zips:
        result = QMessageBox.question(
            parent,
            "Auto-extract ZIP archives?",
            (
                f"{len(zips)} ZIP archive(s) selected.\n\nAuto-extract into "
                "current/? Most state shapefile downloads expect to be "
                "extracted — choose Yes unless the source specifically wants "
                "the ZIP preserved.\n\nIf you say 'No', the ZIPs are copied "
                "as-is."
            ),
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if result == QMessageBox.Cancel:
            return (0, 0, [])
        extract_zips = result == QMessageBox.Yes

    # Pre-check destination overwrites for the copy path. For extracted
    # ZIPs we can't easily predict contents — let safe_extract_zip
    # silently overwrite (matches the fetch pipeline's behavior).
    will_overwrite: list[str] = []
    for src in non_zips:
        if (cur / src.name).exists():
            will_overwrite.append(src.name)
    if not extract_zips:
        for src in zips:
            if (cur / src.name).exists():
                will_overwrite.append(src.name)

    if will_overwrite:
        names = ", ".join(will_overwrite[:5])
        if len(will_overwrite) > 5:
            names += f", and {len(will_overwrite) - 5} more"
        ok = QMessageBox.question(
            parent,
            "Overwrite existing files?",
            (f"These files already exist in current/:\n\n{names}\n\nOverwrite them?"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return (0, 0, [])

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
                # Extract into a same-named subfolder so multi-zip sources
                # like fcc_asr land in current/r_tower/ + current/d_tower/
                # (matching the fetch pipeline's layout). Parcel sources'
                # normalizers use rglob, so subfolders are harmless there.
                sub = cur / zp.stem
                sub.mkdir(parents=True, exist_ok=True)
                files = safe_extract_zip(zp, sub)
                extracted += len(files)
            else:
                shutil.copy2(zp, cur / zp.name)
                copied += 1
        except Exception as e:
            errors.append(f"{zp.name}: {type(e).__name__}: {e}")

    return (copied, extracted, errors)


def mark_manual_install(source: DataSource, manifest: Manifest) -> None:
    """Stamp the manifest entry to reflect a successful manual install.

    Resets ``status`` to ``"ok"``, clears any prior ``fetch_failed`` /
    ``check_failed`` error, refreshes the file list and byte count from
    disk, and recomputes ``next_recommended_check_at`` from the source's
    declared cadence. Called from both the upload button and the
    walkthrough finalize step.
    """
    cur = current_dir(source.id)
    files = [p for p in cur.rglob("*") if p.is_file() and not p.is_symlink()]
    entry = manifest.entry(source.id)
    now = datetime.now(UTC)
    entry.local_version = "manual"
    entry.status = "ok"
    entry.bytes = directory_bytes(cur)
    entry.files = [str(p.relative_to(RAW_ROOT)) for p in files]
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
    manifest.save()
