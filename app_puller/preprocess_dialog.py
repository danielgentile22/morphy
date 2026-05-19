"""Preprocess dialog.

A modal dialog that runs preprocess.runner.run_all() on a QThread, showing
per-source normalize status and per-state compose progress as the worker
streams progress signals.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .workers import PreprocessWorker, make_thread


# Make scripts/ importable for accessing the preprocess registry.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


class PreprocessDialog(QDialog):
    """Modal that drives the preprocess pipeline and shows live progress."""

    def __init__(self, parent=None, *, dark_mode: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preprocess")
        self.resize(900, 660)
        self._dark = dark_mode
        self._worker: Optional[PreprocessWorker] = None
        self._thread: Optional[QThread] = None
        self._source_items: dict[str, QTreeWidgetItem] = {}
        self._state_items: dict[str, QTreeWidgetItem] = {}

        self._build_ui()
        self._populate_tree()

    # ── theming helpers ───────────────────────────────────────────────────

    def _muted_hex(self) -> str:
        return "#bdbdbd" if self._dark else "#616161"

    def _ok_hex(self) -> str:
        return "#81c784" if self._dark else "#2e7d32"

    def _fail_hex(self) -> str:
        return "#e57373" if self._dark else "#c62828"

    # ── UI build ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        # Top controls: state selector + force-rebuild
        top = QHBoxLayout()
        top.addWidget(QLabel("Compose state:"))
        self.state_combo = QComboBox()
        self.state_combo.addItem("All states with parcel data", None)
        self._populate_state_combo()
        top.addWidget(self.state_combo)

        self.force_check = QCheckBox("Force rebuild (re-normalize everything)")
        top.addWidget(self.force_check)
        top.addStretch(1)
        v.addLayout(top)

        # Tree of normalize / compose phases
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Phase", "Status", "Detail"])
        self.tree.setColumnWidth(0, 380)
        self.tree.setColumnWidth(1, 130)
        self.tree.setAlternatingRowColors(True)
        v.addWidget(self.tree, stretch=1)

        # Live activity log
        log_frame = QFrame()
        log_frame.setFrameShape(QFrame.StyledPanel)
        lv = QVBoxLayout(log_frame)
        lv.setContentsMargins(8, 6, 8, 6)
        lv.addWidget(QLabel("Activity"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(140)
        lv.addWidget(self.log)
        v.addWidget(log_frame)

        # Action buttons
        bb = QDialogButtonBox()
        self.btn_run = QPushButton("Run")
        self.btn_run.clicked.connect(self._on_run)  # type: ignore
        self.btn_cancel = QPushButton("Cancel current")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel)  # type: ignore
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)  # type: ignore
        bb.addButton(self.btn_run, QDialogButtonBox.ActionRole)
        bb.addButton(self.btn_cancel, QDialogButtonBox.ActionRole)
        bb.addButton(self.btn_close, QDialogButtonBox.RejectRole)
        v.addWidget(bb)

    def _populate_state_combo(self) -> None:
        try:
            from preprocess import registry  # noqa: F401
            from preprocess.geographies import all_states
            for st in all_states():
                self.state_combo.addItem(f"{st.abbr} — {st.name}", st.fips)
        except Exception as e:
            self._log_line(f"could not enumerate states: {e}", level="warn")

    def _populate_tree(self) -> None:
        self.tree.clear()
        self._source_items.clear()
        self._state_items.clear()

        from preprocess import registry  # noqa: F401
        from preprocess.base import all_normalizers

        norm_root = QTreeWidgetItem(["Normalize", "pending", ""])
        f = norm_root.font(0); f.setBold(True); norm_root.setFont(0, f)
        self.tree.addTopLevelItem(norm_root)
        norm_root.setExpanded(True)
        for n in all_normalizers():
            item = QTreeWidgetItem([n.source_id, "pending", ""])
            norm_root.addChild(item)
            self._source_items[n.source_id] = item

        comp_root = QTreeWidgetItem(["Compose (per state)", "pending", ""])
        f = comp_root.font(0); f.setBold(True); comp_root.setFont(0, f)
        self.tree.addTopLevelItem(comp_root)
        comp_root.setExpanded(True)
        # Rows for states populated dynamically when compose_start fires.

    # ── handlers ──────────────────────────────────────────────────────────

    def _on_run(self) -> None:
        state_fips = self.state_combo.currentData()
        force = self.force_check.isChecked()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.state_combo.setEnabled(False)
        self.force_check.setEnabled(False)
        # Reset row statuses to pending.
        for item in self._source_items.values():
            self._set_status(item, "pending", "", color=self._muted_hex())
        for item in self._state_items.values():
            self.tree.invisibleRootItem().removeChild(item)
        self._state_items.clear()

        self._log_line(
            f"Preprocess starting: state={state_fips or 'all'}, force={force}"
        )

        worker = PreprocessWorker(state_fips=state_fips, force_rebuild=force)
        thread = make_thread(worker)
        worker.progress.connect(self._on_progress)
        worker.all_done.connect(self._on_all_done)
        self._worker = worker
        self._thread = thread
        thread.start()

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._log_line("cancellation requested — will stop after current source")

    def _on_progress(self, phase: str, key: str, info: dict) -> None:
        if phase.startswith("normalize_"):
            item = self._source_items.get(key)
            if item is None:
                return
            if phase == "normalize_start":
                self._set_status(item, "running…", "", color=self._muted_hex())
                self._log_line(f"→ normalize {key}")
            elif phase == "normalize_ok":
                rows = info.get("rows", 0)
                bytes_ = info.get("bytes", 0)
                self._set_status(item, "✓ ok",
                                 f"{rows:,} rows · {bytes_/1_000_000:.1f} MB",
                                 color=self._ok_hex())
                self._log_line(f"✓ {key}: {rows:,} rows")
            elif phase == "normalize_fail":
                err = info.get("error", "")
                self._set_status(item, "✗ FAIL", str(err)[:80],
                                 color=self._fail_hex())
                self._log_line(f"✗ {key}: {err}", level="err")
            elif phase == "normalize_skip":
                reason = info.get("reason", "")
                self._set_status(item, "· skipped", reason,
                                 color=self._muted_hex())
            elif phase == "normalize_unavailable":
                self._set_status(item, "– unavailable", "no raw data",
                                 color=self._muted_hex())
        elif phase.startswith("compose_"):
            item = self._state_items.get(key)
            if phase == "compose_start":
                if item is None:
                    comp_root = self.tree.topLevelItem(1)
                    label = f"{key} ({info.get('name', '')})"
                    item = QTreeWidgetItem([label, "running…", ""])
                    comp_root.addChild(item)
                    self._state_items[key] = item
                self._set_status(item, "running…", "", color=self._muted_hex())
                self._log_line(f"→ compose state {key} ({info.get('name', '')})")
            elif phase == "compose_ok":
                counts = info.get("counts", {})
                summary = ", ".join(f"{k}={v:,}" for k, v in counts.items())
                self._set_status(item, "✓ ok", summary, color=self._ok_hex())
                self._log_line(
                    f"✓ state {key}: joins={info.get('joins', 0)}, "
                    f"views={info.get('views', 0)}, {summary}"
                )
            elif phase == "compose_fail":
                err = info.get("error", "")
                self._set_status(item, "✗ FAIL", str(err)[:80], color=self._fail_hex())
                self._log_line(f"✗ state {key}: {err}", level="err")
        elif phase == "all_done":
            pass  # handled by all_done signal
        elif phase == "error":
            self._log_line(f"FATAL: {info.get('error', '')}", level="err")

    def _on_all_done(self, success: bool, outcome: dict) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
        self._worker = None
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.state_combo.setEnabled(True)
        self.force_check.setEnabled(True)
        if "error" in outcome and not outcome.get("normalized_ok"):
            self._log_line(f"=== FAILED: {outcome['error']}", level="err")
            return
        self._log_line(
            f"=== preprocess complete in {outcome.get('duration_seconds', 0):.1f}s — "
            f"{len(outcome.get('normalized_ok', []))} sources OK, "
            f"{len(outcome.get('composed_ok', []))} states composed, "
            f"{len(outcome.get('normalized_failed', []))} failures"
        )

    # ── helpers ───────────────────────────────────────────────────────────

    def _set_status(self, item: QTreeWidgetItem, status: str, detail: str, *, color: str) -> None:
        from PySide6.QtGui import QColor
        item.setText(1, status)
        item.setText(2, detail)
        item.setForeground(1, QColor(color))

    def _log_line(self, msg: str, *, level: str = "info") -> None:
        muted = self._muted_hex()
        color = self._fail_hex() if level == "err" else (self._muted_hex() if level == "warn" else None)
        if color:
            self.log.append(f'<span style="color:{color}">{msg}</span>')
        else:
            self.log.append(msg)

    def reject(self) -> None:  # type: ignore[override]
        # Don't allow close while a worker is mid-run.
        if self._worker is not None:
            self._log_line("can't close while preprocess is running — Cancel first", level="warn")
            return
        super().reject()
