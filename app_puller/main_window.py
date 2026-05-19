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

from diagnose import DiagnoseUnavailable, diagnose
from fetch import RAW_ROOT
from fetch.base import DataSource
from fetch.legal import AutomationPolicy, CommercialUse
from fetch.manifest import Manifest, SourceEntry
from fetch.registry import all_sources, get_source, grouped
from fetch.storage import current_dir, directory_bytes, human_bytes
from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from verify_raw import verify_all, verify_one

from .preprocess_dialog import PreprocessDialog
from .workers import CheckWorker, FetchWorker

# ── status presentation ──────────────────────────────────────────────────────


STATUS_LABELS = {
    "ok": ("✓ Current", QColor("#2e7d32")),
    "stale": ("⟳ Stale (new version available)", QColor("#ef6c00")),
    "missing": ("✗ Not installed", QColor("#9e9e9e")),
    "check_failed": ("⚠ Check failed", QColor("#c62828")),
    "fetch_failed": ("⚠ Fetch failed", QColor("#c62828")),
    "manual_only": ("⤓ Manual download required", QColor("#5e35b1")),
    "needs_credentials": ("🔒 Credentials required", QColor("#5e35b1")),
}


def status_for(source: DataSource, entry: SourceEntry) -> str:
    """Resolve the displayable status, combining manifest + source policy.

    For MANUAL_ONLY / CREDENTIALED sources, files dropped into current/
    by hand (detected by ``_detect_manual_installs``) should still show
    as ✓ Current — show the install state when present, fall back to
    the policy-restricted state otherwise.
    """
    if source.legal.automation == AutomationPolicy.MANUAL_ONLY:
        if entry.is_installed():
            return "ok"
        return "manual_only"
    if (
        source.legal.automation == AutomationPolicy.CREDENTIALED
        and not source.credentials_available()
    ):
        if entry.is_installed():
            return "ok"
        return "needs_credentials"
    if entry.status in STATUS_LABELS:
        if entry.status == "ok" and entry.is_stale():
            return "stale"
        return entry.status
    return "missing"


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

        # threads / workers held to keep alive
        self._check_thread: QThread | None = None
        self._fetch_thread: QThread | None = None
        self._check_worker: CheckWorker | None = None
        self._fetch_worker: FetchWorker | None = None

        # progress accounting for rate calc
        self._dl_start_ts: float | None = None
        self._dl_start_bytes: int = 0

        self._build_ui()
        self._populate_tree()
        self._refresh_header()

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
            elif not has_files and entry.local_version and entry.status == "ok":
                # User deleted the data manually — reflect that
                entry.local_version = None
                entry.status = "missing"
                entry.files = []
                entry.bytes = 0
        if n_detected > 0:
            self._manifest.save()
        return n_detected

    def _is_dark(self) -> bool:
        bg = self.palette().color(QPalette.Window)
        return bg.lightness() < 128

    def _muted_hex(self) -> str:
        return "#bdbdbd" if self._is_dark() else "#616161"

    def _text_hex(self) -> str:
        return "#eeeeee" if self._is_dark() else "#212121"

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # Header
        outer.addWidget(self._build_header())

        # Action bar
        outer.addWidget(self._build_action_bar())

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

        muted = self._muted_hex()
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
            self.btn_rescan,
            self.btn_verify,
            self.btn_preprocess,
        ):
            b.setMinimumHeight(30)
        self.btn_cancel.setMinimumHeight(30)

        h.addWidget(self.btn_check)
        h.addWidget(self.btn_pull_stale)
        h.addWidget(self.btn_pull_missing)
        h.addWidget(self.btn_rescan)
        h.addWidget(self.btn_verify)
        h.addWidget(self.btn_preprocess)
        h.addStretch(1)
        h.addWidget(self.btn_cancel)
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
        self.det_subtitle.setStyleSheet(f"color: {self._muted_hex()};")
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

        self.btn_manual = QPushButton("Open manual download URL")
        self.btn_manual.setEnabled(False)
        self.btn_manual.clicked.connect(self._open_manual)  # type: ignore
        self.btn_manual.setMinimumHeight(32)

        h.addWidget(self.btn_action)
        h.addWidget(self.btn_manual)
        v.addLayout(h)

        return wrap

    def _build_progress_panel(self) -> QWidget:
        wrap = QFrame()
        wrap.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(wrap)
        v.setContentsMargins(12, 8, 12, 8)

        self.pb_label = QLabel("Idle. No pull in progress.")
        self.pb_label.setStyleSheet(f"color: {self._muted_hex()};")
        v.addWidget(self.pb_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("")
        self.progress.setMinimumHeight(18)
        v.addWidget(self.progress)

        self.pb_substatus = QLabel("")
        self.pb_substatus.setStyleSheet(f"color: {self._muted_hex()}; font-size: 11px;")
        v.addWidget(self.pb_substatus)

        return wrap

    def _build_log_panel(self) -> QWidget:
        wrap = QFrame()
        wrap.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(wrap)
        v.setContentsMargins(12, 8, 12, 8)

        title = QLabel("Activity")
        f = QFont()
        f.setBold(True)
        title.setFont(f)
        v.addWidget(title)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(140)
        v.addWidget(self.log)
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

        status = status_for(source, entry)
        label, color = STATUS_LABELS[status]
        item.setText(COL_STATUS, label)
        item.setForeground(COL_STATUS, color)

        size_bytes = directory_bytes(current_dir(source.id))
        item.setText(COL_SIZE, human_bytes(size_bytes) if size_bytes else "—")

        item.setText(COL_LOCAL, entry.local_version or "—")
        item.setText(COL_REMOTE, entry.remote_version or "—")

        # Action label per state
        if status == "manual_only":
            item.setText(COL_ACTION, "Open manual URL")
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

        muted = self._muted_hex()
        text = self._text_hex()
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

    # ── actions ─────────────────────────────────────────────────────────

    def _on_anchor_clicked(self, url) -> None:
        webbrowser.open(url.toString())

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
        self._start_fetch([s])

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
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)  # type: ignore
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
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)  # type: ignore
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
        self._append_log("Verifying contents of every source folder…")
        QApplication.processEvents()
        results = verify_all()
        self._show_verify_dialog(results, summary_to_log=True)

    def _show_verify_dialog(self, results, summary_to_log: bool = False) -> None:
        from fetch.storage import human_bytes as _hb

        n_ok = sum(1 for r in results if r.verdict == "OK")
        n_fail = sum(1 for r in results if r.verdict in ("FAIL", "EMPTY"))
        n_unknown = sum(1 for r in results if r.verdict == "UNKNOWN")
        n_missing = sum(1 for r in results if r.verdict == "NOT_INSTALLED")

        is_dark = self._is_dark()
        muted = self._muted_hex()
        text = self._text_hex()
        ok_color = "#81c784" if is_dark else "#2e7d32"
        fail_color = "#e57373" if is_dark else "#c62828"
        unknown_color = "#ffd54f" if is_dark else "#f57c00"
        link_color = "#64b5f6" if is_dark else "#1565c0"

        rows = []
        for r in results:
            if r.verdict == "OK":
                color, mark = ok_color, "✓"
            elif r.verdict in ("FAIL", "EMPTY"):
                color, mark = fail_color, "✗"
            elif r.verdict == "UNKNOWN":
                color, mark = unknown_color, "?"
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
                f'style="color:{link_color};text-decoration:none">'
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
            f'<span style="color:{ok_color}"><b>{n_ok} OK</b></span> &nbsp;·&nbsp; '
            f'<span style="color:{fail_color}"><b>{n_fail} failing</b></span> &nbsp;·&nbsp; '
            f'<span style="color:{muted}">{n_missing} not installed</span>'
            + (
                f' &nbsp;·&nbsp; <span style="color:{unknown_color}">{n_unknown} unknown</span>'
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
        text = self._text_hex()
        muted = self._muted_hex()

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

        dlg.show()
        QApplication.processEvents()

        buf: list[str] = []

        def on_chunk(text_chunk: str) -> None:
            buf.append(text_chunk)
            joined = "".join(buf).replace("\n", "<br>")
            body.setHtml(f'<div style="color:{text}">{joined}</div>')
            cursor = body.textCursor()
            cursor.movePosition(cursor.End)
            body.setTextCursor(cursor)
            QApplication.processEvents()

        try:
            diagnose(result, on_chunk=on_chunk)
        except DiagnoseUnavailable as e:
            body.setHtml(f'<div style="color:{muted}">Diagnosis unavailable.<br><br>{e}</div>')

        dlg.exec()

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
        self._teardown_thread("check")
        self._append_log("Check complete.")

    def _on_fetch_started(self, source_id: str, name: str) -> None:
        self._dl_start_ts = time.monotonic()
        self._dl_start_bytes = 0
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
        self._teardown_thread("fetch")
        self._append_log("All pulls complete.")

    def _teardown_thread(self, kind: str) -> None:
        if kind == "check" and self._check_thread:
            self._check_thread.quit()
            self._check_thread.wait(2000)
            self._check_thread = None
            self._check_worker = None
        elif kind == "fetch" and self._fetch_thread:
            self._fetch_thread.quit()
            self._fetch_thread.wait(2000)
            self._fetch_thread = None
            self._fetch_worker = None

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
        for b in (self.btn_check, self.btn_pull_stale, self.btn_pull_missing):
            b.setEnabled(not busy)
        if hasattr(self, "btn_action"):
            self.btn_action.setEnabled(not busy and bool(getattr(self, "_current_source_id", None)))

    def _append_log(self, msg: str, error: bool = False) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        muted = self._muted_hex()
        prefix = f"<span style='color:{muted}'>[{ts}]</span> "
        color = (
            "#e57373" if error and self._is_dark() else ("#c62828" if error else self._text_hex())
        )
        self.log.append(f"{prefix}<span style='color:{color}'>{msg}</span>")

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
        try:
            self._manifest.save()
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
