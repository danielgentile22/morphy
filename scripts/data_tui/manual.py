"""Manual-path screens: guided walkthrough + install-from-file (#237).

Both are thin shells over the headless ``fetch.install`` engine. The walkthrough
renders a source's ``ManualWalkthrough`` steps (deep links open in the
OS browser); install-from-file accepts typed or terminal-dragged paths,
including ZIPs, and produces the manual-upload layout the normalizers
already read.
"""

from __future__ import annotations

import shlex
import webbrowser
from pathlib import Path

from fetch.base import DataSource
from fetch.install import install_files, mark_manual_install
from fetch.manifest import Manifest
from fetch.storage import current_dir, directory_bytes
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Static


def parse_paths(text: str) -> list[Path]:
    """Split typed/dragged path input. Terminal drag-and-drop pastes
    shell-escaped paths (backslash-escaped spaces or quotes) — shlex
    undoes both."""
    return [Path(p).expanduser() for p in shlex.split(text)]


class InstallScreen(ModalScreen[list[Path] | None]):
    """Prompt for one or more file paths; dismisses with validated Paths."""

    BINDINGS = [("escape", "cancel", "Cancel")]
    CSS = """
    InstallScreen { align: center middle; }
    #install-box {
        width: 80%;
        height: auto;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    #install-error { color: $error; }
    """

    def __init__(self, source: DataSource) -> None:
        super().__init__()
        self.source = source

    def compose(self) -> ComposeResult:
        with Vertical(id="install-box"):
            yield Static(
                Text.assemble(
                    ("Install files for ", "bold"),
                    (self.source.name, "bold"),
                    f" → data/raw/{self.source.id}/current/\n",
                    ("Type or drag file paths (ZIPs auto-extract), Enter to install.", "dim"),
                )
            )
            yield Input(placeholder="/path/to/download.zip")
            yield Static(id="install-error")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            self.dismiss(None)
            return
        try:
            paths = parse_paths(text)
        except ValueError as e:
            self.query_one("#install-error", Static).update(f"Could not parse paths: {e}")
            return
        missing = [str(p) for p in paths if not p.is_file()]
        if missing:
            self.query_one("#install-error", Static).update("Not found: " + ", ".join(missing))
            return
        self.dismiss(paths)

    def action_cancel(self) -> None:
        self.dismiss(None)


class WalkthroughScreen(ModalScreen[bool]):
    """Step-by-step manual-download guide; dismisses True after a
    verified install."""

    BINDINGS = [
        ("n", "next", "Next / finish"),
        ("b", "back", "Back"),
        ("o", "open_link", "Open link"),
        ("i", "install", "Install files"),
        ("escape", "close", "Close"),
    ]
    CSS = """
    WalkthroughScreen { align: center middle; }
    #walk-body {
        width: 90%;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    """

    def __init__(self, source: DataSource, manifest: Manifest) -> None:
        super().__init__()
        walkthrough = source.manual_walkthrough()
        if walkthrough is None:
            raise ValueError(f"{source.id} has no manual_walkthrough()")
        self.source = source
        self.manifest = manifest
        self.walkthrough = walkthrough
        self.step_index = 0
        self._notice = ""
        self._notice_error = False
        self.lines: list[str] = []  # plain-text mirror for Textual Pilot tests

    def compose(self) -> ComposeResult:
        yield Static(id="walk-body")
        yield Footer()

    def on_mount(self) -> None:
        self._repaint()

    def _repaint(self) -> None:
        wt = self.walkthrough
        step = wt.steps[self.step_index]
        total = len(wt.steps)
        last = self.step_index == total - 1
        lines = [
            f"{self.source.name} — manual download",
            f"Step {self.step_index + 1} of {total}: {step.title}",
            step.body,
        ]
        if step.deep_link:
            lines.append(f"Link (o): {step.deep_link}")
        lines.append(f"Landing page: {wt.landing_page_url}")
        if wt.expected_files:
            lines.append("Expected in current/: " + ", ".join(wt.expected_files))
        lines.append(
            "[n] I'm done — verify & finish   [b] back   [i] install files   [esc] close"
            if last
            else "[n] next   [b] back   [i] install files   [esc] close"
        )
        if self._notice:
            lines.append(self._notice)
        self.lines = lines

        body = Text(lines[0], style="bold")
        body.append(f"\n{lines[1]}", style="bold cyan")
        for line in lines[2:-1] if self._notice else lines[2:]:
            body.append(f"\n{line}")
        if self._notice:
            body.append(f"\n{self._notice}", style="bold red" if self._notice_error else "green")
        self.query_one("#walk-body", Static).update(body)

    def _set_notice(self, msg: str, *, error: bool = False) -> None:
        self._notice = msg
        self._notice_error = error
        self._repaint()

    # ── actions ─────────────────────────────────────────────────────────

    def action_next(self) -> None:
        if self.step_index < len(self.walkthrough.steps) - 1:
            self.step_index += 1
            self._notice = ""
            self._repaint()
        else:
            self._finalize()

    def action_back(self) -> None:
        if self.step_index > 0:
            self.step_index -= 1
            self._notice = ""
            self._repaint()

    def action_open_link(self) -> None:
        step = self.walkthrough.steps[self.step_index]
        webbrowser.open(step.deep_link or self.walkthrough.landing_page_url)

    def action_install(self) -> None:
        self.app.push_screen(InstallScreen(self.source), self._install_done)

    def _install_done(self, paths: list[Path] | None) -> None:
        if not paths:
            return
        copied, extracted, errors = install_files(self.source.id, paths)
        if errors:
            self._set_notice("Install errors: " + "; ".join(errors), error=True)
        else:
            self._set_notice(
                f"✓ Installed: {copied} copied, {extracted} extracted → "
                f"data/raw/{self.source.id}/current/"
            )

    def action_close(self) -> None:
        self.dismiss(False)

    # ── finalize ─────────────────────────────────────────────────────────

    def _finalize(self) -> None:
        cur = current_dir(self.source.id)
        cur.mkdir(parents=True, exist_ok=True)
        if directory_bytes(cur) == 0:
            self._set_notice(
                f"No files found in {cur} yet — install them (i) or drop the "
                "download there, then finish again.",
                error=True,
            )
            return
        files = [p for p in cur.rglob("*") if p.is_file() and not p.is_symlink()]
        try:
            self.source.validate(files)
        except Exception as e:  # noqa: BLE001 — any validation failure stays in-screen
            notes = self.walkthrough.notes_on_failure or ""
            self._set_notice(
                f"Validation failed: {type(e).__name__}: {e}" + (f" — {notes}" if notes else ""),
                error=True,
            )
            return
        mark_manual_install(self.source, self.manifest)
        self.dismiss(True)
