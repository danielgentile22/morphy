"""Upload files from anywhere on disk into a source's ``current/`` dir.

Used by the puller's details pane and the walkthrough modal so the user
doesn't have to navigate to ``data/raw/<id>/current/`` by hand after a
manual download. Files default to the user's Desktop in the file picker
because that's the most common landing spot for manual downloads.

ZIP archives are auto-extractable (matching the puller's existing
fetch-then-extract pattern). Overwrites are confirmed once at the top
to keep the flow non-modal-heavy.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fetch.base import DataSource
from fetch.sources._helpers import safe_extract_zip
from fetch.storage import current_dir
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
                files = safe_extract_zip(zp, cur)
                extracted += len(files)
            else:
                shutil.copy2(zp, cur / zp.name)
                copied += 1
        except Exception as e:
            errors.append(f"{zp.name}: {type(e).__name__}: {e}")

    return (copied, extracted, errors)
