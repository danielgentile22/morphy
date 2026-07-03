"""Manual-install support: Qt shell over the headless ``fetch.install``.

The copy/extract/stamp engine lives in ``fetch.install`` (PRD #233
slice 3) so the data TUI shares it. This module keeps only the Qt
parts: the file picker and the auto-extract / overwrite confirmation
dialogs, then delegates to the headless functions. User-visible
behavior is unchanged from the pre-extraction version.
"""

from __future__ import annotations

from pathlib import Path

from fetch import install as headless
from fetch.base import DataSource
from fetch.manifest import Manifest
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
    zips = [p for p in paths if p.suffix.lower() == ".zip"]

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

    will_overwrite = headless.overwrite_conflicts(source.id, paths, extract_zips=extract_zips)
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

    return headless.install_files(source.id, paths, extract_zips=extract_zips)


def mark_manual_install(source: DataSource, manifest: Manifest) -> None:
    """Stamp the manifest as a successful manual install and save it.

    Thin wrapper over ``fetch.install.mark_manual_install`` that keeps
    the pre-extraction contract (stamp + save in one call) for the two
    Qt call sites.
    """
    headless.mark_manual_install(source, manifest)
    manifest.save()
