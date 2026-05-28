"""Pilot Data Puller — main window.

Layout:

  ┌──────────────────────────────────────────────────────────────────┐
  │  header bar  ·  total storage  ·  last full check                │
  │  [Check for updates]  [Pull all stale]  [Pull all missing]       │
  ├────────────────────────────────────┬─────────────────────────────┤
  │  source tree (category groups)     │  details panel              │
  │  ┌─ TOWERS                        │  • description              │
  │  │   FCC ASR        ✓ Current ... │  • source URL (clickable)   │
  │  │   FCC ULS Cell   ⟳ Stale  ...  │  • license / commercial     │
  │  │   ...                          │  • automation policy        │
  │  ├─ SOLAR                         │  • update cadence           │
  │  ├─ BILLBOARDS                    │  • size on disk             │
  │  ├─ PARCELS                       │  • [Pull / Re-pull]         │
  │  └─ DISTRESS                      │  • [Open manual URL]        │
  ├────────────────────────────────────┴─────────────────────────────┤
  │  currently-pulling label                                         │
  │  [████████████░░░░░░░░░] 62% — 112.0 MB / 180.4 MB · 4.2 MB/s    │
  ├──────────────────────────────────────────────────────────────────┤
  │  activity log (most recent first)                                │
  └──────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import sys
import time
import webbrowser
from datetime import UTC, datetime

from fetch import RAW_ROOT
from fetch.base import DataSource
from fetch.legal import AutomationPolicy, CommercialUse
from fetch.manifest import (
    FRESHNESS_STALE,
    Manifest,
    SourceEntry,
)
from fetch.registry import all_sources, get_source, grouped
from fetch.storage import current_dir, directory_bytes, human_bytes
from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from verify_raw import verify_one

from . import state as ui_state
from .attention_panel import AttentionItem, attention_items
from .preprocess_dialog import PreprocessDialog
from .status import (
    FRESHNESS_COLORS,
    STATUS_LABELS,
    freshness_label_for,
    status_for,
)
from .theme import Palette, is_dark
from .manual_install import mark_manual_install, pick_and_upload
from .walkthrough_dialog import WalkthroughDialog
from .workers import (
    CheckWorker,
    DiagnoseWorker,
    FetchWorker,
    VerifyWorker,
    make_thread,
    stop_thread,
)

# ── columns ──────────────────────────────────────────────────────────────────

COL_NAME = 0
COL_STATUS = 1
COL_SIZE = 2
COL_LOCAL = 3
COL_REMOTE = 4
COL_ACTION = 5


# ── main window ──────────────────────────────────────────────────────────────


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pilot Data Puller")
        self.resize(1280, 820)

        self._manifest = Manifest.load()
        self._sources = all_sources()
        self._items: dict[str, QTreeWidgetItem] = {}

        self._prune_orphan_manifest_entries()
        self._detect_manual_installs()
        self._sync_cadence_from_sources()

        # threads / workers held to keep alive
        self._check_thread: QThread | None = None
        self._fetch_thread: QThread | None = None
        self._verify_thread: QThread | None = None
        self._diagnose_thread: QThread | None = None
        self._check_worker: CheckWorker | None = None
        self._fetch_worker: FetchWorker | None = None
        self._verify_worker: VerifyWorker | None = None
        self._diagnose_worker: DiagnoseWorker | None = None

        # progress accounting for rate calc
        self._dl_start_ts: float | None = None

        # Queue of manual sources to walk through after a bulk auto-fetch.
        self._pending_manual_queue: list[DataSource] = []

        self._build_ui()
        self._populate_tree()
        self._refresh_header()
        self._refresh_attention_panel()
        self._restore_ui_state()

        # Recompute size figures periodically so the user sees totals
        # update even when nothing is downloading.
        self._size_timer = QTimer(self)
        self._size_timer.timeout.connect(self._refresh_header)  # type: ignore
        self._size_timer.start(5000)

    # ── chrome / construction ───────────────────────────────────────────

    def _prune_orphan_manifest_entries(self) -> int:
        """Drop manifest entries for source IDs no longer in the registry."""
        known = {s.id for s in self._sources}
        orphans = [sid for sid in self._manifest.sources if sid not in known]
        for sid in orphans:
            del self._manifest.sources[sid]
        if orphans:
            self._manifest.save()
        return len(orphans)

    def _detect_manual_installs(self) -> int:
        """Mark sources as installed if files were dropped into current/ by hand.

        Sets local_version='manual' / status='ok' for any source whose
        current/ directory has files but whose manifest entry has no
        local_version. Returns the number of newly-detected installs.
        """
        n_detected = 0
        for s in self._sources:
            entry = self._manifest.entry(s.id)
            cur = current_dir(s.id)
            has_files = directory_bytes(cur) > 0
            if has_files and not entry.local_version:
                files = [
                    str(p.relative_to(RAW_ROOT))
                    for p in cur.rglob("*")
                    if p.is_file() and not p.is_symlink()
                ]
                entry.local_version = "manual"
                entry.status = "ok"
                entry.bytes = directory_bytes(cur)
                entry.files = files
                entry.error = None
                if entry.fetched_at is None:
                    from datetime import datetime

                    entry.fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
                n_detected += 1
            elif (
                has_files
                and entry.local_version == "manual"
                and entry.status in ("fetch_failed", "check_failed")
            ):
                # Stale failure stamp: files were re-installed manually
                # after a prior auto-fetch failed. Clear the failure so the
                # UI matches disk reality. Refresh the file inventory too.
                files = [
                    str(p.relative_to(RAW_ROOT))
                    for p in cur.rglob("*")
                    if p.is_file() and not p.is_symlink()
                ]
                entry.status = "ok"
                entry.error = None
                entry.bytes = directory_bytes(cur)
                entry.files = files
                n_detected += 1
            elif not has_files and entry.local_version and entry.status == "ok":
                # User deleted the data manually — reflect that
                entry.local_version = None
                entry.status = "missing"
                entry.files = []
                entry.bytes = 0
        if n_detected > 0:
            self._manifest.save()
        return n_detected

    def _sync_cadence_from_sources(self) -> None:
        """Reflect each source's declared cadence into the manifest.

        Lets the freshness column show real values immediately, before
        the user runs 'Check for updates' for the first time after the
        v1 → v2 schema migration.
        """
        changed = False
        for s in self._sources:
            e = self._manifest.entry(s.id)
            if e.update_cadence_days != s.update_cadence_days:
                self._manifest.update_cadence(s.id, s.update_cadence_days)
                changed = True
        if changed:
            self._manifest.save()

    def _is_dark(self) -> bool:
        return is_dark(self)

    def _palette(self) -> Palette:
        return Palette.for_widget(self)

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # Header
        outer.addWidget(self._build_header())

        # Action bar
        outer.addWidget(self._build_action_bar())

        # "What needs my attention" panel (hidden when empty)
        outer.addWidget(self._build_attention_panel())

        # Search/filter row
        outer.addWidget(self._build_search_row())

        # Splitter: tree on the left, details on the right
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_tree())
        splitter.addWidget(self._build_details_pane())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([780, 460])
        outer.addWidget(splitter, stretch=1)

        # Progress
        outer.addWidget(self._build_progress_panel())

        # Activity log
        outer.addWidget(self._build_log_panel(), stretch=0)

        self.setCentralWidget(central)

    def _build_header(self) -> QWidget:
        wrap = QFrame()
        wrap.setFrameShape(QFrame.StyledPanel)
        h = QHBoxLayout(wrap)
        h.setContentsMargins(12, 8, 12, 8)

        title = QLabel("Pilot Data Puller")
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        title.setFont(f)
        h.addWidget(title)
        h.addStretch(1)

        muted = self._palette().muted
        self.lbl_storage = QLabel("…")
        self.lbl_storage.setStyleSheet(f"color: {muted};")
        h.addWidget(self.lbl_storage)

        sep = QLabel("·")
        sep.setStyleSheet(f"color: {muted}; margin: 0 8px;")
        h.addWidget(sep)

        self.lbl_last_check = QLabel("…")
        self.lbl_last_check.setStyleSheet(f"color: {muted};")
        h.addWidget(self.lbl_last_check)

        return wrap

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)

        self.btn_check = QPushButton("Check for updates")
        self.btn_check.clicked.connect(self._start_check_all)  # type: ignore

        self.btn_pull_stale = QPushButton("Pull all stale")
        self.btn_pull_stale.clicked.connect(self._pull_stale)  # type: ignore

        self.btn_pull_missing = QPushButton("Pull all missing")
        self.btn_pull_missing.clicked.connect(self._pull_missing)  # type: ignore

        self.btn_refresh_assisted = QPushButton("Refresh all stale (with prompts)")
        self.btn_refresh_assisted.setToolTip(
            "Pull every stale auto source, then walk through every stale "
            "manual source one at a time with the guided walkthrough modal."
        )
        self.btn_refresh_assisted.clicked.connect(self._refresh_all_stale_assisted)  # type: ignore

        self.btn_rescan = QPushButton("Rescan disk")
        self.btn_rescan.setToolTip(
            "Detect files dropped manually into data/raw/<source_id>/current/"
        )
        self.btn_rescan.clicked.connect(self._rescan_disk)  # type: ignore

        self.btn_verify = QPushButton("Verify contents")
        self.btn_verify.setToolTip(
            "Check every installed source folder for required files and "
            "flag any wrong/missing data before preprocessing"
        )
        self.btn_verify.clicked.connect(self._verify_contents)  # type: ignore

        self.btn_preprocess = QPushButton("Preprocess")
        self.btn_preprocess.setToolTip(
            "Normalize every installed source into canonical schemas, then "
            "compose per-state joined outputs the map app can load"
        )
        self.btn_preprocess.clicked.connect(self._open_preprocess_dialog)  # type: ignore

        self.btn_cancel = QPushButton("Cancel current pull")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_active)  # type: ignore

        for b in (
            self.btn_check,
            self.btn_pull_stale,
            self.btn_pull_missing,
            self.btn_refresh_assisted,
            self.btn_rescan,
            self.btn_verify,
            self.btn_preprocess,
        ):
            b.setMinimumHeight(30)
        self.btn_cancel.setMinimumHeight(30)

        h.addWidget(self.btn_check)
        h.addWidget(self.btn_pull_stale)
        h.addWidget(self.btn_pull_missing)
        h.addWidget(self.btn_refresh_assisted)
        h.addWidget(self.btn_rescan)
        h.addWidget(self.btn_verify)
        h.addWidget(self.btn_preprocess)
        h.addStretch(1)
        h.addWidget(self.btn_cancel)
        return bar

    def _build_attention_panel(self) -> QWidget:
        """Top-of-window aggregator: every source that needs human action.

        Hidden when empty. Each row has a one-click action button:
          - Manual source / missing manual → "Walk me through"
          - Auto source past cadence       → "Refresh"
          - Endpoint failing               → "Diagnose" + "Open URL"
        """
        wrap = QFrame()
        wrap.setObjectName("attentionPanel")
        wrap.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(wrap)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(6)

        title_row = QHBoxLayout()
        self.lbl_attention_title = QLabel("⚠ What needs my attention")
        f = QFont()
        f.setBold(True)
        self.lbl_attention_title.setFont(f)
        title_row.addWidget(self.lbl_attention_title)
        title_row.addStretch(1)
        v.addLayout(title_row)

        self.attention_scroll = QScrollArea()
        self.attention_scroll.setWidgetResizable(True)
        self.attention_scroll.setFrameShape(QFrame.NoFrame)
        self.attention_scroll.setMaximumHeight(140)
        self.attention_container = QWidget()
        self.attention_layout = QVBoxLayout(self.attention_container)
        self.attention_layout.setContentsMargins(0, 0, 0, 0)
        self.attention_layout.setSpacing(4)
        self.attention_layout.addStretch(1)
        self.attention_scroll.setWidget(self.attention_container)
        v.addWidget(self.attention_scroll)

        self.attention_panel = wrap
        return wrap

    def _build_search_row(self) -> QWidget:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel("Search:")
        lbl.setStyleSheet(f"color: {self._palette().muted};")
        h.addWidget(lbl)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter sources by name or ID…")
        self.search_box.textChanged.connect(self._on_search_changed)  # type: ignore
        self.search_box.setClearButtonEnabled(True)
        h.addWidget(self.search_box, stretch=1)

        self.lbl_match_count = QLabel("")
        self.lbl_match_count.setStyleSheet(f"color: {self._palette().muted}; font-size: 11px;")
        h.addWidget(self.lbl_match_count)

        return bar

    def _build_tree(self) -> QWidget:
        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(
            ["Source", "Status", "Local size", "Local version", "Remote version", "Action"]
        )
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.SingleSelection)
        self.tree.currentItemChanged.connect(self._on_select)  # type: ignore

        h = self.tree.header()
        h.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        h.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_LOCAL, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_REMOTE, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_ACTION, QHeaderView.ResizeToContents)
        return self.tree

    def _build_details_pane(self) -> QWidget:
        wrap = QFrame()
        wrap.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(wrap)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        self.det_title = QLabel("Select a source")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        self.det_title.setFont(f)
        self.det_title.setWordWrap(True)
        v.addWidget(self.det_title)

        self.det_subtitle = QLabel("")
        self.det_subtitle.setStyleSheet(f"color: {self._palette().muted};")
        self.det_subtitle.setWordWrap(True)
        v.addWidget(self.det_subtitle)

        self.det_body = QTextBrowser()
        self.det_body.setReadOnly(True)
        self.det_body.setOpenLinks(False)
        self.det_body.setOpenExternalLinks(False)
        self.det_body.anchorClicked.connect(self._on_anchor_clicked)  # type: ignore
        v.addWidget(self.det_body, stretch=1)

        h = QHBoxLayout()
        self.btn_action = QPushButton("Pull")
        self.btn_action.setEnabled(False)
        self.btn_action.clicked.connect(self._pull_current)  # type: ignore
        self.btn_action.setMinimumHeight(32)

        self.btn_upload = QPushButton("⤴ Upload file(s)…")
        self.btn_upload.setEnabled(False)
        self.btn_upload.setToolTip(
            "Pick file(s) from anywhere on disk (e.g. your Desktop) and "
            "copy them straight into data/raw/<source>/current/. ZIPs can "
            "be auto-extracted."
        )
        self.btn_upload.clicked.connect(self._upload_for_current)  # type: ignore
        self.btn_upload.setMinimumHeight(32)

        self.btn_manual = QPushButton("Open manual download URL")
        self.btn_manual.setEnabled(False)
        self.btn_manual.clicked.connect(self._open_manual)  # type: ignore
        self.btn_manual.setMinimumHeight(32)

        h.addWidget(self.btn_action)
        h.addWidget(self.btn_upload)
        h.addWidget(self.btn_manual)
        v.addLayout(h)

        return wrap

    def _build_progress_panel(self) -> QWidget:
        wrap = QFrame()
        wrap.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(wrap)
        v.setContentsMargins(12, 8, 12, 8)

        self.pb_label = QLabel("Idle. No pull in progress.")
        self.pb_label.setStyleSheet(f"color: {self._palette().muted};")
        v.addWidget(self.pb_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("")
        self.progress.setMinimumHeight(18)
        v.addWidget(self.progress)

        self.pb_substatus = QLabel("")
        self.pb_substatus.setStyleSheet(f"color: {self._palette().muted}; font-size: 11px;")
        v.addWidget(self.pb_substatus)

        return wrap

    def _build_log_panel(self) -> QWidget:
        wrap = QFrame()
        wrap.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(wrap)
        v.setContentsMargins(12, 8, 12, 8)

        title_row = QHBoxLayout()
        title = QLabel("Activity")
        f = QFont()
        f.setBold(True)
        title.setFont(f)
        title_row.addWidget(title)
        title_row.addStretch(1)

        title_row.addWidget(QLabel("Filter:"))
        self.log_filter = QComboBox()
        self.log_filter.addItem("All", "all")
        self.log_filter.addItem("Errors only", "errors")
        self.log_filter.currentIndexChanged.connect(self._on_log_filter_changed)  # type: ignore
        title_row.addWidget(self.log_filter)

        self.btn_copy_log = QToolButton()
        self.btn_copy_log.setText("Copy")
        self.btn_copy_log.setToolTip("Copy visible activity log to clipboard")
        self.btn_copy_log.clicked.connect(self._copy_log_to_clipboard)  # type: ignore
        title_row.addWidget(self.btn_copy_log)

        v.addLayout(title_row)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(140)
        v.addWidget(self.log)

        # In-memory log buffer for filter-aware re-render.
        # Each entry: (timestamp_str, msg, is_error)
        self._log_entries: list[tuple[str, str, bool]] = []
        return wrap

    # ── tree population ─────────────────────────────────────────────────

    def _populate_tree(self) -> None:
        self.tree.clear()
        self._items.clear()

        for category, sources in grouped().items():
            if not sources:
                continue
            cat_item = QTreeWidgetItem([category, "", "", "", "", ""])
            f = QFont()
            f.setBold(True)
            cat_item.setFont(COL_NAME, f)
            self.tree.addTopLevelItem(cat_item)
            cat_item.setExpanded(True)
            for s in sources:
                row = QTreeWidgetItem([s.name, "", "", "", "", ""])
                row.setData(COL_NAME, Qt.UserRole, s.id)
                cat_item.addChild(row)
                self._items[s.id] = row
                self._refresh_row(s)
        self.tree.resizeColumnToContents(COL_STATUS)

    def _refresh_row(self, source: DataSource) -> None:
        entry = self._manifest.entry(source.id)
        item = self._items[source.id]

        label, color = freshness_label_for(source, entry)
        item.setText(COL_STATUS, label)
        item.setForeground(COL_STATUS, color)

        size_bytes = directory_bytes(current_dir(source.id))
        item.setText(COL_SIZE, human_bytes(size_bytes) if size_bytes else "—")

        item.setText(COL_LOCAL, entry.local_version or "—")
        item.setText(COL_REMOTE, entry.remote_version or "—")

        # Action label per state — manual sources with walkthroughs get a
        # distinct call-to-action; others fall back to install/pull verbs.
        status = status_for(source, entry)
        has_walkthrough = source.manual_walkthrough() is not None
        if status == "manual_only":
            item.setText(COL_ACTION, "Walk me through" if has_walkthrough else "Open manual URL")
        elif status == "needs_credentials":
            item.setText(COL_ACTION, "Configure creds")
        elif status == "ok" and not entry.is_stale():
            item.setText(COL_ACTION, "Re-pull")
        elif status in ("stale", "missing", "fetch_failed", "check_failed"):
            item.setText(COL_ACTION, "Pull")
        else:
            item.setText(COL_ACTION, "")

    def _refresh_all_rows(self) -> None:
        for s in self._sources:
            self._refresh_row(s)
        self._refresh_header()
        self._refresh_attention_panel()

    def _refresh_header(self) -> None:
        total = directory_bytes(RAW_ROOT)
        n_installed = sum(1 for s in self._sources if self._manifest.entry(s.id).is_installed())
        self.lbl_storage.setText(
            f"Total raw data: <b>{human_bytes(total)}</b>  "
            f"·  installed: <b>{n_installed} / {len(self._sources)} sources</b>  "
            f"·  path: <code>{RAW_ROOT}</code>"
        )
        lc = self._manifest.last_full_check
        if lc:
            self.lbl_last_check.setText(f"Last update check: {lc}")
        else:
            self.lbl_last_check.setText("Last update check: never")

    # ── selection / details ─────────────────────────────────────────────

    def _on_select(self, current: QTreeWidgetItem | None, _prev) -> None:
        if current is None or current.parent() is None:
            self._show_no_selection()
            return
        sid = current.data(COL_NAME, Qt.UserRole)
        if not sid:
            self._show_no_selection()
            return
        try:
            s = get_source(sid)
        except KeyError:
            self._show_no_selection()
            return
        self._show_source(s)

    def _show_no_selection(self) -> None:
        self.det_title.setText("Select a source")
        self.det_subtitle.setText("")
        self.det_body.setHtml("")
        self.btn_action.setEnabled(False)
        self.btn_upload.setEnabled(False)
        self.btn_manual.setEnabled(False)
        self._current_source_id: str | None = None

    def _show_source(self, s: DataSource) -> None:
        self._current_source_id = s.id
        entry = self._manifest.entry(s.id)
        status = status_for(s, entry)
        status_label, _ = STATUS_LABELS[status]

        self.det_title.setText(s.name)
        self.det_subtitle.setText(f"{s.category}  ·  {s.coverage}  ·  updated {s.cadence}")

        bytes_local = directory_bytes(current_dir(s.id))

        def esc(v) -> str:
            from html import escape

            return escape(str(v)) if v is not None else "—"

        automation_explain = {
            AutomationPolicy.ALLOWED: (
                "Publisher provides an explicit bulk-download endpoint. Safe to pull automatically."
            ),
            AutomationPolicy.TOLERATED: (
                "No explicit bulk endpoint, but published files are linked "
                "from a public page. Pulled politely with a single GET; "
                "User-Agent identifies this tool."
            ),
            AutomationPolicy.MANUAL_ONLY: (
                "Publisher does not permit automated download (terms of "
                "service, click-through, captcha, or no stable URL). "
                "Use the manual download URL below; drop the resulting "
                "file into the source's <code>current/</code> folder."
            ),
            AutomationPolicy.CREDENTIALED: (
                "Paid / credentialed source. Will only pull when the "
                "documented environment variables are set."
            ),
        }[s.legal.automation]

        commercial_label = {
            CommercialUse.ALLOWED: "✅ Commercial use OK",
            CommercialUse.ALLOWED_WITH_ATTRIBUTION: "✅ Commercial use OK with attribution",
            CommercialUse.RESTRICTED: "⛔ Restricted — verify before commercial use",
            CommercialUse.UNKNOWN: "❓ Unknown — verify before commercial use",
        }[s.legal.commercial_use]

        notes = s.legal.notes or ""

        muted = self._palette().muted
        text = self._palette().text
        is_dark = self._is_dark()
        badge_bg = "#37474f" if is_dark else "#eceff1"
        badge_fg = "#eceff1" if is_dark else "#37474f"
        err_color = "#e57373" if is_dark else "#c62828"
        body = f"""
        <style>
          p {{ margin: 4px 0; }}
          .k {{ color: {muted}; font-weight: 600; }}
          .v {{ color: {text}; }}
          .badge {{
            display: inline-block; padding: 2px 8px; border-radius: 10px;
            background: {badge_bg}; color: {badge_fg}; font-size: 11px;
          }}
        </style>
        <p><b>Status:</b> <span class="v">{esc(status_label)}</span></p>
        <p><b>Description:</b> {esc(s.description)}</p>
        <p><b>Estimated download size:</b> ~{s.estimated_size_mb:,.0f} MB
           &nbsp;·&nbsp; <b>On disk now:</b> {human_bytes(bytes_local)}</p>
        <p><b>Local version:</b> <span class="v">{esc(entry.local_version)}</span>
           &nbsp;·&nbsp; <b>Remote version:</b> <span class="v">{esc(entry.remote_version)}</span></p>
        <p><b>Last fetched:</b> {esc(entry.fetched_at)}
           &nbsp;·&nbsp; <b>Last checked:</b> {esc(entry.checked_at)}</p>
        <hr>
        <p><span class="k">Publisher:</span> {esc(s.legal.publisher)}</p>
        <p><span class="k">License:</span> {esc(s.legal.license)}</p>
        <p><span class="k">Commercial use:</span> {esc(commercial_label)}</p>
        <p><span class="k">Automation policy:</span>
           <span class="badge">{esc(s.legal.automation.value)}</span> &nbsp; {automation_explain}</p>
        <p><span class="k">Source page:</span>
           <a href="{esc(s.legal.manual_url)}">{esc(s.legal.manual_url)}</a></p>
        {('<p><span class="k">Attribution:</span> ' + esc(s.legal.attribution) + "</p>") if s.legal.attribution else ""}
        {('<p><span class="k">Notes:</span> ' + esc(notes) + "</p>") if notes else ""}
        {('<p style="color:' + err_color + '"><b>Last error:</b> ' + esc(entry.error) + "</p>") if entry.error else ""}
        """
        self.det_body.setHtml(body)

        # Buttons
        if s.legal.automation == AutomationPolicy.MANUAL_ONLY:
            if s.manual_walkthrough() is not None:
                self.btn_action.setEnabled(self._fetch_thread is None)
                self.btn_action.setText("▶ Walk me through")
            else:
                self.btn_action.setEnabled(False)
                self.btn_action.setText("Manual download required")
        elif s.legal.automation == AutomationPolicy.CREDENTIALED and not s.credentials_available():
            self.btn_action.setEnabled(False)
            self.btn_action.setText("Credentials required (see notes)")
        else:
            self.btn_action.setEnabled(self._fetch_thread is None)
            if entry.is_installed() and not entry.is_stale():
                self.btn_action.setText("Re-pull")
            elif entry.is_stale():
                self.btn_action.setText("Pull (stale)")
            else:
                self.btn_action.setText("Pull")
        self.btn_manual.setEnabled(bool(s.legal.manual_url))
        # Upload is available for any source — useful even for auto sources
        # when the auto-fetch is failing and the user grabbed it by hand.
        self.btn_upload.setEnabled(self._fetch_thread is None)

    # ── actions ─────────────────────────────────────────────────────────

    def _on_anchor_clicked(self, url) -> None:
        webbrowser.open(url.toString())

    def _upload_for_current(self) -> None:
        sid = getattr(self, "_current_source_id", None)
        if not sid:
            return
        s = get_source(sid)
        result = pick_and_upload(s, self)
        if result is None:
            self._append_log(f"Upload cancelled for {s.name}.")
            return
        copied, extracted, errors = result
        if copied == 0 and extracted == 0 and not errors:
            self._append_log(f"Upload for {s.name}: nothing copied (overwrite declined).")
            return
        parts = []
        if copied:
            parts.append(f"copied {copied} file(s)")
        if extracted:
            parts.append(f"extracted {extracted} from ZIP(s)")
        msg = f"Upload for {s.name}: {', '.join(parts)} → data/raw/{s.id}/current/."
        self._append_log(msg)
        for err in errors:
            self._append_log(f"  ✗ {err}", error=True)

        # Always reset the manifest entry on a successful upload — this
        # clears any prior fetch_failed / check_failed left over from an
        # earlier auto-fetch attempt. Without this the status column
        # would stay at "Fetch failed" even though files are now on disk.
        if (copied or extracted) and not errors:
            mark_manual_install(s, self._manifest)

        self._refresh_all_rows()
        if getattr(self, "_current_source_id", None) == sid:
            self._show_source(s)

    def _open_manual(self) -> None:
        if not getattr(self, "_current_source_id", None):
            return
        s = get_source(self._current_source_id)
        webbrowser.open(s.legal.manual_url)

    def _pull_current(self) -> None:
        sid = getattr(self, "_current_source_id", None)
        if not sid:
            return
        s = get_source(sid)
        # MANUAL_ONLY sources with a walkthrough open the guided modal
        # instead of trying to auto-fetch.
        if (
            s.legal.automation == AutomationPolicy.MANUAL_ONLY
            and s.manual_walkthrough() is not None
        ):
            self._open_walkthrough_for(s)
            return
        self._start_fetch([s])

    def _open_walkthrough_for(self, source: DataSource) -> None:
        """Open the guided walkthrough modal; refresh row on success."""
        try:
            dlg = WalkthroughDialog(source, self._manifest, self, dark_mode=self._is_dark())
        except ValueError as e:
            self._append_log(f"Cannot open walkthrough for {source.name}: {e}", error=True)
            return
        self._append_log(f"Walkthrough opened for {source.name}.")
        dlg.exec()
        if dlg.completed:
            self._append_log(f"✓ Manual install completed for {source.name}.")
            self._refresh_all_rows()
            if getattr(self, "_current_source_id", None) == source.id:
                self._show_source(source)
        else:
            self._append_log(f"Walkthrough closed without completion: {source.name}.")

    def _pull_stale(self) -> None:
        targets = []
        for s in self._sources:
            e = self._manifest.entry(s.id)
            status = status_for(s, e)
            if status == "stale":
                targets.append(s)
        if not targets:
            QMessageBox.information(
                self,
                "Nothing stale",
                "No sources have a newer version available. "
                "Run 'Check for updates' first if you suspect this is wrong.",
            )
            return
        self._start_fetch(targets)

    def _pull_missing(self) -> None:
        targets = []
        for s in self._sources:
            e = self._manifest.entry(s.id)
            status = status_for(s, e)
            if status == "missing":
                targets.append(s)
        if not targets:
            QMessageBox.information(
                self, "Nothing missing", "Every automatable source is already installed."
            )
            return
        self._start_fetch(targets)

    def _start_check_all(self) -> None:
        if self._check_thread is not None:
            return
        self._set_buttons_busy(True)
        self._append_log(f"Checking remote versions for {len(self._sources)} sources…")

        worker = CheckWorker(self._sources, self._manifest)
        thread = make_thread(worker, parent=self)
        worker.progress.connect(self._on_check_progress)
        worker.one_done.connect(self._on_check_one_done)
        worker.all_done.connect(self._on_check_all_done)
        self._check_worker = worker
        self._check_thread = thread
        thread.start()

    def _start_fetch(self, sources: list[DataSource]) -> None:
        if self._fetch_thread is not None:
            QMessageBox.warning(self, "Already running", "A pull is already in progress.")
            return

        # Filter MANUAL_ONLY immediately — show a single info dialog if any
        manuals = [s for s in sources if s.legal.automation == AutomationPolicy.MANUAL_ONLY]
        sources = [s for s in sources if s.legal.automation != AutomationPolicy.MANUAL_ONLY]

        if manuals:
            names = "\n".join(f" · {s.name}\n     {s.legal.manual_url}" for s in manuals)
            QMessageBox.information(
                self,
                "Manual downloads required",
                "The following sources do not permit automated download. "
                "Please use these URLs manually:\n\n" + names,
            )

        if not sources:
            return

        self._set_buttons_busy(True)
        self.btn_cancel.setEnabled(True)
        self._append_log(f"Starting pull for {len(sources)} source(s).")

        worker = FetchWorker(sources, self._manifest)
        thread = make_thread(worker, parent=self)
        worker.started.connect(self._on_fetch_started)
        worker.progress.connect(self._on_fetch_progress)
        worker.one_done.connect(self._on_fetch_one_done)
        worker.all_done.connect(self._on_fetch_all_done)
        self._fetch_worker = worker
        self._fetch_thread = thread
        thread.start()

    def _rescan_disk(self) -> None:
        n = self._detect_manual_installs()
        self._refresh_all_rows()
        if n > 0:
            self._append_log(f"Rescan: detected {n} manually-installed source(s).")
        else:
            self._append_log("Rescan: no new manually-installed sources found.")

    def _open_preprocess_dialog(self) -> None:
        dlg = PreprocessDialog(self, dark_mode=self._is_dark())
        self._append_log("Preprocess dialog opened.")
        dlg.exec()
        self._append_log("Preprocess dialog closed.")

    def _verify_contents(self) -> None:
        if self._verify_thread is not None:
            return  # already running
        self._append_log("Verifying contents of every source folder…")
        self.btn_verify.setEnabled(False)

        worker = VerifyWorker()
        thread = make_thread(worker, parent=self)
        worker.done.connect(self._on_verify_done)
        worker.failed.connect(self._on_verify_failed)
        self._verify_worker = worker
        self._verify_thread = thread
        thread.start()

    def _on_verify_done(self, results: list) -> None:
        self._teardown_thread("verify")
        self.btn_verify.setEnabled(True)
        self._show_verify_dialog(results, summary_to_log=True)

    def _on_verify_failed(self, msg: str) -> None:
        self._teardown_thread("verify")
        self.btn_verify.setEnabled(True)
        self._append_log(f"Verify failed: {msg}", error=True)

    def _show_verify_dialog(self, results, summary_to_log: bool = False) -> None:
        from fetch.storage import human_bytes as _hb

        n_ok = sum(1 for r in results if r.verdict == "OK")
        n_fail = sum(1 for r in results if r.verdict in ("FAIL", "EMPTY"))
        n_unknown = sum(1 for r in results if r.verdict == "UNKNOWN")
        n_missing = sum(1 for r in results if r.verdict == "NOT_INSTALLED")

        p = self._palette()
        muted, text = p.muted, p.text

        rows = []
        for r in results:
            if r.verdict == "OK":
                color, mark = p.ok, "✓"
            elif r.verdict in ("FAIL", "EMPTY"):
                color, mark = p.fail, "✗"
            elif r.verdict == "UNKNOWN":
                color, mark = p.warn, "?"
            else:  # NOT_INSTALLED
                color, mark = muted, "·"
            size = _hb(r.nbytes) if r.nbytes else "—"
            label_html = (
                f'<div style="color:{muted};font-size:11px;margin-left:24px">'
                f"expected: {r.label}</div>"
                if r.label and r.verdict in ("FAIL", "EMPTY")
                else ""
            )
            diag_link = (
                f' &nbsp;<a href="diagnose:{r.source_id}" '
                f'style="color:{p.link};text-decoration:none">'
                f"[Diagnose with AI]</a>"
                if r.verdict in ("FAIL", "EMPTY")
                else ""
            )
            rows.append(
                f'<div style="margin:4px 0">'
                f'<span style="color:{color};font-weight:bold">{mark} {r.source_id}</span> '
                f'<span style="color:{muted}">— {size}</span>'
                f"{diag_link}<br>"
                f'<span style="color:{text};margin-left:24px">{r.detail}</span>'
                f"{label_html}</div>"
            )

        summary = (
            f'<div style="font-size:13px;margin-bottom:8px">'
            f'<span style="color:{p.ok}"><b>{n_ok} OK</b></span> &nbsp;·&nbsp; '
            f'<span style="color:{p.fail}"><b>{n_fail} failing</b></span> &nbsp;·&nbsp; '
            f'<span style="color:{muted}">{n_missing} not installed</span>'
            + (
                f' &nbsp;·&nbsp; <span style="color:{p.warn}">{n_unknown} unknown</span>'
                if n_unknown
                else ""
            )
            + "</div>"
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Verify raw data contents")
        dlg.resize(860, 620)
        v = QVBoxLayout(dlg)
        header = QLabel(summary)
        header.setTextFormat(Qt.RichText)
        v.addWidget(header)
        body = QTextBrowser()
        body.setOpenLinks(False)
        body.setOpenExternalLinks(False)
        body.anchorClicked.connect(  # type: ignore[attr-defined]
            lambda url, parent=dlg: self._on_verify_anchor(url, parent)
        )
        body.setHtml("".join(rows))
        v.addWidget(body, stretch=1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)
        dlg.exec()

        if summary_to_log:
            if n_fail > 0:
                self._append_log(
                    f"Verify: {n_ok} OK, {n_fail} failing — preprocessing will be unsafe.",
                    error=True,
                )
            else:
                self._append_log(f"Verify: {n_ok} OK, no failures.")

    def _on_verify_anchor(self, url, parent_dialog) -> None:
        scheme = url.scheme()
        if scheme != "diagnose":
            webbrowser.open(url.toString())
            return
        source_id = url.path() or url.toString().split(":", 1)[1]
        self._diagnose_one(source_id, parent_dialog)

    def _diagnose_one(self, source_id: str, parent) -> None:
        result = verify_one(source_id)
        text = self._palette().text
        muted = self._palette().muted

        dlg = QDialog(parent)
        dlg.setWindowTitle(f"Diagnose: {source_id}")
        dlg.resize(720, 520)
        v = QVBoxLayout(dlg)

        header = QLabel(
            f'<div style="font-size:13px;color:{text}"><b>{source_id}</b></div>'
            f'<div style="color:{muted};font-size:11px;margin-top:2px">'
            f"verify reason: {result.detail}</div>"
        )
        header.setTextFormat(Qt.RichText)
        header.setWordWrap(True)
        v.addWidget(header)

        body = QTextBrowser()
        body.setHtml(
            f'<div style="color:{muted};font-style:italic">Asking Claude to diagnose…</div>'
        )
        v.addWidget(body, stretch=1)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)

        buf: list[str] = []

        def on_chunk(text_chunk: str) -> None:
            buf.append(text_chunk)
            joined = "".join(buf).replace("\n", "<br>")
            body.setHtml(f'<div style="color:{text}">{joined}</div>')
            cursor = body.textCursor()
            cursor.movePosition(cursor.End)
            body.setTextCursor(cursor)

        def on_failed(msg: str) -> None:
            body.setHtml(f'<div style="color:{muted}">{msg.replace(chr(10), "<br>")}</div>')

        worker = DiagnoseWorker(source_id)
        thread = make_thread(worker, parent=dlg)
        worker.chunk.connect(on_chunk)
        worker.failed.connect(on_failed)
        # Closing the dialog must reap the thread; we don't expose a cancel
        # hook on DiagnoseWorker (the Anthropic stream is short and cheap),
        # but quit()+wait() ensures we don't leak the QThread.
        self._diagnose_worker = worker
        self._diagnose_thread = thread
        thread.start()

        dlg.exec()
        self._teardown_thread("diagnose")

    def _cancel_active(self) -> None:
        if self._fetch_worker:
            self._fetch_worker.cancel()
            self._append_log("Cancellation requested. Finishing current chunk…")
        if self._check_worker:
            self._check_worker.cancel()

    # ── worker signal handlers ──────────────────────────────────────────

    def _on_check_progress(self, source_id: str, text: str) -> None:
        self.pb_label.setText(text)

    def _on_check_one_done(self, source_id: str, ok: bool, msg: str) -> None:
        try:
            s = get_source(source_id)
        except KeyError:
            return
        if ok:
            self._append_log(f"checked {s.name} → remote version: {msg}")
        else:
            self._append_log(f"check failed for {s.name}: {msg}", error=True)
        self._refresh_row(s)
        if getattr(self, "_current_source_id", None) == source_id:
            self._show_source(s)

    def _on_check_all_done(self) -> None:
        self._set_buttons_busy(False)
        self.pb_label.setText("Idle. No pull in progress.")
        self._refresh_header()
        self._refresh_attention_panel()
        self._teardown_thread("check")
        self._append_log("Check complete.")

    def _on_fetch_started(self, source_id: str, name: str) -> None:
        self._dl_start_ts = time.monotonic()
        self.pb_label.setText(f"Downloading: {name}")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.pb_substatus.setText("Starting…")
        self._append_log(f"→ pulling {name}…")

    def _on_fetch_progress(
        self, source_id: str, bytes_done: int, bytes_total: int, fname: str
    ) -> None:
        if bytes_total > 0:
            self.progress.setRange(0, bytes_total)
            self.progress.setValue(min(bytes_done, bytes_total))
            pct = (bytes_done / bytes_total) * 100
            done_str = human_bytes(bytes_done)
            tot_str = human_bytes(bytes_total)
            rate = self._rate(bytes_done)
            self.pb_substatus.setText(f"{fname} — {done_str} / {tot_str}  ({pct:.1f}%)   {rate}")
            self.progress.setFormat(f"{pct:.1f}%")
        else:
            # Indeterminate
            self.progress.setRange(0, 0)
            rate = self._rate(bytes_done)
            self.pb_substatus.setText(
                f"{fname} — {human_bytes(bytes_done)} (size unknown)   {rate}"
            )

    def _on_fetch_one_done(self, source_id: str, ok: bool, msg: str) -> None:
        try:
            s = get_source(source_id)
        except KeyError:
            return
        prefix = "✓" if ok else "✗"
        self._append_log(f"{prefix} {s.name}: {msg}", error=not ok)
        self._refresh_row(s)
        self._refresh_header()
        if getattr(self, "_current_source_id", None) == source_id:
            self._show_source(s)

    def _on_fetch_all_done(self) -> None:
        self._set_buttons_busy(False)
        self.btn_cancel.setEnabled(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("")
        self.pb_label.setText("Idle. No pull in progress.")
        self.pb_substatus.setText("")
        self._refresh_header()
        self._refresh_attention_panel()
        self._teardown_thread("fetch")
        self._append_log("All pulls complete.")

        # If an assisted bulk refresh queued manual walkthroughs, process them.
        if self._pending_manual_queue:
            QTimer.singleShot(0, self._process_pending_manuals)

    def _teardown_thread(self, kind: str) -> None:
        if kind == "check":
            stop_thread(self._check_thread)
            self._check_thread = None
            self._check_worker = None
        elif kind == "fetch":
            stop_thread(self._fetch_thread)
            self._fetch_thread = None
            self._fetch_worker = None
        elif kind == "verify":
            stop_thread(self._verify_thread)
            self._verify_thread = None
            self._verify_worker = None
        elif kind == "diagnose":
            stop_thread(self._diagnose_thread)
            self._diagnose_thread = None
            self._diagnose_worker = None

    # ── utils ───────────────────────────────────────────────────────────

    def _rate(self, bytes_done: int) -> str:
        if self._dl_start_ts is None:
            return ""
        dt = time.monotonic() - self._dl_start_ts
        if dt < 0.5:
            return ""
        rate = bytes_done / dt
        return f"{human_bytes(int(rate))}/s"

    def _set_buttons_busy(self, busy: bool) -> None:
        for b in (
            self.btn_check,
            self.btn_pull_stale,
            self.btn_pull_missing,
            self.btn_refresh_assisted,
        ):
            b.setEnabled(not busy)
        has_selection = bool(getattr(self, "_current_source_id", None))
        if hasattr(self, "btn_action"):
            self.btn_action.setEnabled(not busy and has_selection)
        if hasattr(self, "btn_upload"):
            self.btn_upload.setEnabled(not busy and has_selection)

    # ── attention panel ─────────────────────────────────────────────────

    def _attention_items(self) -> list[AttentionItem]:
        return attention_items(self._sources, self._manifest)

    def _refresh_attention_panel(self) -> None:
        # Clear existing rows (keep the trailing stretch).
        while self.attention_layout.count() > 1:
            child = self.attention_layout.takeAt(0)
            w = child.widget() if child else None
            if w is not None:
                w.deleteLater()

        items = self._attention_items()
        if not items:
            self.lbl_attention_title.setText("✓ All sources current")
            self.attention_panel.hide()
            return

        self.lbl_attention_title.setText(
            f"⚠ What needs my attention ({len(items)} source{'s' if len(items) != 1 else ''})"
        )
        muted = self._palette().muted
        for it in items:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            lbl = QLabel(
                f"<b>{it.source.id}</b> &nbsp; <span style='color:{muted}'>{it.reason}</span>"
            )
            lbl.setTextFormat(Qt.RichText)
            lbl.setWordWrap(True)
            h.addWidget(lbl, stretch=1)

            if it.action == "walkthrough":
                btn = QPushButton("▶ Walk me through")
                btn.clicked.connect(  # type: ignore
                    lambda _checked=False, s=it.source: self._open_walkthrough_for(s)
                )
            elif it.action == "refresh":
                btn = QPushButton("↻ Refresh")
                btn.clicked.connect(  # type: ignore
                    lambda _checked=False, s=it.source: self._start_fetch([s])
                )
            else:  # open_manual
                btn = QPushButton("Open URL")
                btn.clicked.connect(  # type: ignore
                    lambda _checked=False, s=it.source: webbrowser.open(s.legal.manual_url)
                )
            btn.setMinimumHeight(26)
            h.addWidget(btn)

            self.attention_layout.insertWidget(self.attention_layout.count() - 1, row)
        self.attention_panel.show()

    # ── search/filter ───────────────────────────────────────────────────

    def _on_search_changed(self, text: str) -> None:
        needle = text.strip().lower()
        total_visible = 0
        for i in range(self.tree.topLevelItemCount()):
            cat_item = self.tree.topLevelItem(i)
            any_visible = False
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                sid = child.data(COL_NAME, Qt.UserRole) or ""
                name = child.text(COL_NAME).lower()
                if not needle or needle in name or needle in sid.lower():
                    child.setHidden(False)
                    any_visible = True
                    total_visible += 1
                else:
                    child.setHidden(True)
            cat_item.setHidden(not any_visible)

        if needle:
            self.lbl_match_count.setText(f"{total_visible} match(es)")
        else:
            self.lbl_match_count.setText("")

    # ── assisted bulk refresh ───────────────────────────────────────────

    def _refresh_all_stale_assisted(self) -> None:
        """Pull every stale auto source, then walk through every stale manual.

        Anything past `next_recommended_check_at` OR with remote_version
        diverging from local OR `status="missing"` is treated as stale.
        Manual sources without a walkthrough are skipped with a notice.
        """
        if self._fetch_thread is not None or self._pending_manual_queue:
            QMessageBox.warning(
                self, "Already running", "An assisted refresh is already in progress."
            )
            return

        auto_targets: list[DataSource] = []
        manual_targets: list[DataSource] = []
        skipped_no_walkthrough: list[DataSource] = []

        for s in self._sources:
            e = self._manifest.entry(s.id)
            needs = (
                not e.is_installed()
                or e.is_stale()
                or e.freshness() == FRESHNESS_STALE
                or e.status in ("check_failed", "fetch_failed")
            )
            if not needs:
                continue
            if s.legal.automation == AutomationPolicy.MANUAL_ONLY:
                if s.manual_walkthrough() is not None:
                    manual_targets.append(s)
                else:
                    skipped_no_walkthrough.append(s)
            elif (
                s.legal.automation == AutomationPolicy.CREDENTIALED
                and not s.credentials_available()
            ):
                # Credentialed-no-creds — surface but don't enqueue
                skipped_no_walkthrough.append(s)
            else:
                auto_targets.append(s)

        if not auto_targets and not manual_targets:
            QMessageBox.information(
                self,
                "Nothing to refresh",
                "All sources are current. Run 'Check for updates' first if you "
                "suspect this is wrong.",
            )
            return

        summary = (
            f"Assisted refresh will run for {len(auto_targets) + len(manual_targets)} "
            f"source(s):\n\n"
            f"  • {len(auto_targets)} auto source(s) pulled in background\n"
            f"  • {len(manual_targets)} manual source(s) — one walkthrough at a time\n"
        )
        if skipped_no_walkthrough:
            names = ", ".join(s.id for s in skipped_no_walkthrough)
            summary += (
                f"\nSkipping ({len(skipped_no_walkthrough)} without walkthrough "
                f"or credentials): {names}\n"
            )
        summary += "\nProceed?"
        ok = QMessageBox.question(
            self,
            "Refresh all stale",
            summary,
            QMessageBox.Yes | QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        self._pending_manual_queue = list(manual_targets)
        self._append_log(
            f"Assisted refresh: {len(auto_targets)} auto, {len(manual_targets)} manual queued."
        )
        if auto_targets:
            self._start_fetch(auto_targets)
        else:
            self._process_pending_manuals()

    def _process_pending_manuals(self) -> None:
        """Pop and walk through queued manual sources sequentially."""
        if not self._pending_manual_queue:
            self._append_log("Assisted refresh complete.")
            self._refresh_attention_panel()
            return
        s = self._pending_manual_queue.pop(0)
        self._open_walkthrough_for(s)
        # Use a 0-delay singleshot so the modal fully closes before the next
        # opens — avoids nested-modal weirdness on macOS.
        QTimer.singleShot(0, self._process_pending_manuals)

    def _append_log(self, msg: str, error: bool = False) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_entries.append((ts, msg, error))
        if self._log_filter_allows(error):
            self.log.append(self._render_log_line(ts, msg, error))

    def _render_log_line(self, ts: str, msg: str, error: bool) -> str:
        muted = self._palette().muted
        prefix = f"<span style='color:{muted}'>[{ts}]</span> "
        p = self._palette()
        color = p.fail if error else p.text
        return f"{prefix}<span style='color:{color}'>{msg}</span>"

    def _log_filter_allows(self, error: bool) -> bool:
        mode = self.log_filter.currentData() if hasattr(self, "log_filter") else "all"
        if mode == "errors":
            return error
        return True

    def _on_log_filter_changed(self, _idx: int) -> None:
        self.log.clear()
        for ts, msg, error in self._log_entries:
            if self._log_filter_allows(error):
                self.log.append(self._render_log_line(ts, msg, error))

    def _copy_log_to_clipboard(self) -> None:
        text = self.log.toPlainText()
        QApplication.clipboard().setText(text)
        self._append_log(f"Copied {len(text)} chars of activity log to clipboard.")

    # ── persisted state ─────────────────────────────────────────────────

    def _restore_ui_state(self) -> None:
        s = ui_state.load()
        geom = s.get("window")
        if isinstance(geom, dict):
            try:
                x = int(geom.get("x", 0))
                y = int(geom.get("y", 0))
                w = int(geom.get("w", self.width()))
                h = int(geom.get("h", self.height()))
                if w >= 800 and h >= 600:
                    self.move(x, y)
                    self.resize(w, h)
            except (TypeError, ValueError):
                pass

        log_mode = s.get("log_filter")
        if log_mode in ("all", "errors"):
            idx = self.log_filter.findData(log_mode)
            if idx >= 0:
                self.log_filter.setCurrentIndex(idx)

        last_sid = s.get("last_source_id")
        if isinstance(last_sid, str) and last_sid in self._items:
            self.tree.setCurrentItem(self._items[last_sid])

        collapsed = s.get("collapsed_categories") or []
        if isinstance(collapsed, list):
            for i in range(self.tree.topLevelItemCount()):
                cat = self.tree.topLevelItem(i)
                if cat.text(COL_NAME) in collapsed:
                    cat.setExpanded(False)

    def _save_ui_state(self) -> None:
        collapsed: list[str] = []
        for i in range(self.tree.topLevelItemCount()):
            cat = self.tree.topLevelItem(i)
            if not cat.isExpanded():
                collapsed.append(cat.text(COL_NAME))
        state: dict = {
            "window": {
                "x": self.x(),
                "y": self.y(),
                "w": self.width(),
                "h": self.height(),
            },
            "log_filter": self.log_filter.currentData() if hasattr(self, "log_filter") else "all",
            "last_source_id": getattr(self, "_current_source_id", None),
            "collapsed_categories": collapsed,
        }
        ui_state.save(state)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # If a download is running, ask before quitting
        if self._fetch_thread is not None:
            res = QMessageBox.question(
                self,
                "Pull in progress",
                "A data pull is still running. Quit anyway?\n"
                "(In-progress download will be discarded.)",
                QMessageBox.Yes | QMessageBox.No,
            )
            if res != QMessageBox.Yes:
                event.ignore()
                return
            if self._fetch_worker:
                self._fetch_worker.cancel()
                self._fetch_thread.wait(3000)
        if self._check_thread is not None:
            if self._check_worker:
                self._check_worker.cancel()
                self._check_thread.wait(2000)
        stop_thread(self._verify_thread)
        stop_thread(self._diagnose_thread)
        try:
            self._manifest.save()
        except Exception:
            pass
        try:
            self._save_ui_state()
        except Exception:
            pass
        event.accept()


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Pilot Data Puller")
    app.setApplicationDisplayName("Pilot Data Puller")

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
