"""Walkthrough modal for MANUAL_ONLY sources.

Walks the user step-by-step through a guided manual-download flow.
On "I'm done", validates the resulting files in
``data/raw/<source_id>/current/`` and updates the manifest as a
manual install.
"""

from __future__ import annotations

import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fetch import RAW_ROOT
from fetch.base import DataSource
from fetch.manifest import Manifest
from fetch.storage import current_dir, directory_bytes
from fetch.walkthroughs import ManualStep
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class WalkthroughDialog(QDialog):
    """Guided manual-download flow with prev/next nav and final validate."""

    def __init__(
        self,
        source: DataSource,
        manifest: Manifest,
        parent: QWidget | None = None,
        dark_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        walkthrough = source.manual_walkthrough()
        if walkthrough is None:
            raise ValueError(f"{source.id} has no manual_walkthrough()")
        self._source = source
        self._manifest = manifest
        self._walkthrough = walkthrough
        self._dark = dark_mode
        self._completed = False
        self._step_index = 0

        self.setWindowTitle(f"Walk me through: {source.name}")
        self.resize(760, 700)
        self._build_ui()
        self._show_step(0)

    @property
    def completed(self) -> bool:
        return self._completed

    # ── helpers ─────────────────────────────────────────────────────────

    def _muted(self) -> str:
        return "#bdbdbd" if self._dark else "#616161"

    def _text(self) -> str:
        return "#eeeeee" if self._dark else "#212121"

    def _err(self) -> str:
        return "#e57373" if self._dark else "#c62828"

    # ── construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        header_row = QHBoxLayout()
        lbl_title = QLabel(self._source.name)
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        lbl_title.setFont(f)
        header_row.addWidget(lbl_title)
        header_row.addStretch(1)
        self.lbl_counter = QLabel("")
        self.lbl_counter.setStyleSheet(f"color: {self._muted()};")
        header_row.addWidget(self.lbl_counter)
        v.addLayout(header_row)

        landing = self._walkthrough.landing_page_url
        self.lbl_landing = QLabel(f'Landing page: <a href="{landing}">{landing}</a>')
        self.lbl_landing.setStyleSheet(f"color: {self._muted()}; font-size: 11px;")
        self.lbl_landing.setOpenExternalLinks(False)
        self.lbl_landing.linkActivated.connect(self._open_url)  # type: ignore
        self.lbl_landing.setWordWrap(True)
        v.addWidget(self.lbl_landing)

        if self._walkthrough.expected_files:
            self.lbl_expected = QLabel(
                "Expected files in <code>current/</code>: "
                + ", ".join(f"<code>{p}</code>" for p in self._walkthrough.expected_files)
            )
            self.lbl_expected.setStyleSheet(f"color: {self._muted()}; font-size: 11px;")
            self.lbl_expected.setWordWrap(True)
            v.addWidget(self.lbl_expected)

        self.body = QTextBrowser()
        self.body.setOpenLinks(False)
        self.body.setOpenExternalLinks(False)
        self.body.anchorClicked.connect(  # type: ignore
            lambda u: self._open_url(u.toString())
        )
        v.addWidget(self.body, stretch=1)

        self.screenshot_wrap = QScrollArea()
        self.screenshot_wrap.setWidgetResizable(True)
        self.screenshot_label = QLabel("")
        self.screenshot_label.setAlignment(Qt.AlignCenter)
        self.screenshot_wrap.setWidget(self.screenshot_label)
        self.screenshot_wrap.setMinimumHeight(120)
        self.screenshot_wrap.setMaximumHeight(280)
        v.addWidget(self.screenshot_wrap)

        self.btn_deep_link = QPushButton("Open this step's link")
        self.btn_deep_link.setMinimumHeight(30)
        self.btn_deep_link.clicked.connect(self._open_current_deep_link)  # type: ignore
        v.addWidget(self.btn_deep_link)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"color: {self._err()};")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setTextFormat(Qt.RichText)
        self.lbl_error.hide()
        v.addWidget(self.lbl_error)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("← Prev")
        self.btn_prev.setMinimumHeight(32)
        self.btn_prev.clicked.connect(self._prev_step)  # type: ignore
        nav.addWidget(self.btn_prev)
        nav.addStretch(1)
        self.btn_close = QPushButton("Close")
        self.btn_close.setMinimumHeight(32)
        self.btn_close.clicked.connect(self.reject)  # type: ignore
        nav.addWidget(self.btn_close)
        self.btn_next = QPushButton("Next →")
        self.btn_next.setMinimumHeight(32)
        self.btn_next.setDefault(True)
        self.btn_next.clicked.connect(self._next_step)  # type: ignore
        nav.addWidget(self.btn_next)
        v.addLayout(nav)

    # ── step lifecycle ──────────────────────────────────────────────────

    def _step(self) -> ManualStep:
        return self._walkthrough.steps[self._step_index]

    def _show_step(self, idx: int) -> None:
        self._step_index = idx
        step = self._step()
        total = len(self._walkthrough.steps)
        self.lbl_counter.setText(f"Step {idx + 1} of {total}")
        self.body.setMarkdown(f"### {step.title}\n\n{step.body}")
        self._show_screenshot(step)

        if step.deep_link:
            self.btn_deep_link.setText(f"Open in browser: {step.deep_link}")
            self.btn_deep_link.show()
        else:
            self.btn_deep_link.hide()

        self.btn_prev.setEnabled(idx > 0)
        if idx == total - 1:
            self.btn_next.setText("I'm done — verify & finish")
        else:
            self.btn_next.setText("Next →")
        self.lbl_error.hide()

    def _show_screenshot(self, step: ManualStep) -> None:
        if step.screenshot is None:
            self.screenshot_wrap.hide()
            return

        path = Path(step.screenshot)
        if not path.is_absolute():
            # Walkthroughs use repo-relative paths (e.g. "app_puller/assets/...")
            repo_root = Path(__file__).resolve().parent.parent
            path = repo_root / path

        if path.exists():
            pix = QPixmap(str(path))
            if not pix.isNull():
                scaled = pix.scaledToWidth(680, Qt.SmoothTransformation)
                self.screenshot_label.setPixmap(scaled)
                self.screenshot_label.setStyleSheet("")
                self.screenshot_wrap.show()
                return

        # Path declared but file isn't there — show a neutral placeholder
        # so the spec is visible (avoids "missing entirely" silent UX).
        self.screenshot_label.setPixmap(QPixmap())
        self.screenshot_label.setText(f"(screenshot not present: {path.name})")
        self.screenshot_label.setStyleSheet(f"color: {self._muted()};")
        self.screenshot_wrap.show()

    def _open_current_deep_link(self) -> None:
        step = self._step()
        if step.deep_link:
            self._open_url(step.deep_link)

    @staticmethod
    def _open_url(url: str) -> None:
        webbrowser.open(url)

    def _prev_step(self) -> None:
        if self._step_index > 0:
            self._show_step(self._step_index - 1)

    def _next_step(self) -> None:
        if self._step_index < len(self._walkthrough.steps) - 1:
            self._show_step(self._step_index + 1)
        else:
            self._finalize()

    # ── finalize ────────────────────────────────────────────────────────

    def _finalize(self) -> None:
        """Verify files dropped into current/, run validate(), update manifest."""
        cur = current_dir(self._source.id)
        cur.mkdir(parents=True, exist_ok=True)

        if directory_bytes(cur) == 0:
            self._show_error(
                "No files found in <code>"
                f"{cur}</code> yet — drop the downloaded file(s) into this "
                "folder, then click <b>I'm done</b> again."
            )
            return

        files = [p for p in cur.rglob("*") if p.is_file() and not p.is_symlink()]
        try:
            self._source.validate(files)
        except Exception as e:
            notes = self._walkthrough.notes_on_failure or ""
            self._show_error(
                f"Validation failed: {type(e).__name__}: {e}"
                + (f"<br><br><i>{notes}</i>" if notes else "")
            )
            return

        entry = self._manifest.entry(self._source.id)
        now = datetime.now(UTC)
        entry.local_version = "manual"
        entry.status = "ok"
        entry.bytes = directory_bytes(cur)
        entry.files = [str(p.relative_to(RAW_ROOT)) for p in files]
        entry.error = None
        entry.fetched_at = now.isoformat(timespec="seconds")
        entry.checked_at = entry.fetched_at
        cadence = self._source.update_cadence_days
        entry.update_cadence_days = cadence
        if cadence is not None:
            entry.next_recommended_check_at = (now + timedelta(days=cadence)).isoformat(
                timespec="seconds"
            )
        else:
            entry.next_recommended_check_at = None
        self._manifest.save()
        self._completed = True
        self.accept()

    def _show_error(self, msg_html: str) -> None:
        self.lbl_error.setText(msg_html)
        self.lbl_error.show()
