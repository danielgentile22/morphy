"""Verify + confirm-gated deploy screen (#239).

Thin shell over the pure ``verify`` module and the ``deploy`` driver.
The phase machine enforces the gates: a failed verify blocks deploy
until an explicit override (logged to the activity feed); apply only
runs after the dry-run output has been shown and confirmed; escape is
ignored while a leg is running (never abandon a sync mid-flight). A
successful apply writes the deploy receipt that baselines the next
verify; a smoke failure is rendered as an unmissable banner and fires
a desktop notification.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Log, Static

from . import deploy as deploy_mod
from . import verify as verify_mod
from .notify import send as notify_send

# Phase machine: verify → dry_running → confirm → applying → done.
# Overriding a failed verify keeps the phase at "verify" but unlocks [d].


class DeployScreen(ModalScreen[str | None]):
    """Render the verify report, then drive dry-run → confirm → apply."""

    BINDINGS = [
        ("o", "override", "Override failed verify"),
        ("d", "dry_run", "Dry-run"),
        ("a", "apply", "Apply to prod"),
        ("escape", "close", "Close"),
    ]
    CSS = """
    DeployScreen { align: center middle; }
    #deploy-box {
        width: 90%;
        height: 85%;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    #deploy-report { height: auto; max-height: 50%; }
    #deploy-output { height: 1fr; border: round $secondary; }
    #deploy-status { height: auto; }
    """

    def __init__(
        self,
        on_activity: Callable[[str, bool], None] = lambda msg, err: None,
        composite_dir: Path | None = None,
        receipt_path: Path | None = None,
        script: Path | None = None,
        restart_argv: tuple[str, ...] | None = None,
    ) -> None:
        super().__init__()
        self.on_activity = on_activity
        self._composite_dir = composite_dir
        self._receipt_path = receipt_path
        self._script = script
        self._restart_argv = restart_argv
        self.phase = "verify"
        self.overridden = False
        self.result_summary: str | None = None
        self.lines: list[str] = []  # verify-report mirror for Textual Pilot tests
        self.status_line = ""  # current status/keys mirror
        self.output_lines: list[str] = []  # streamed deploy output mirror

    def compose(self) -> ComposeResult:
        with Vertical(id="deploy-box"):
            yield Static(id="deploy-report")
            yield Log(id="deploy-output")
            yield Static(id="deploy-status")
        yield Footer()

    def on_mount(self) -> None:
        # Resolve defaults at mount so tests can monkeypatch the module
        # constants (same pattern as fetch.storage.RAW_ROOT).
        self._composite_dir = self._composite_dir or verify_mod.COMPOSITE_ROOT
        self._receipt_path = self._receipt_path or verify_mod.RECEIPT_PATH
        self._script = self._script or deploy_mod.DEPLOY_SCRIPT
        self._restart_argv = self._restart_argv or deploy_mod.RESTART_ARGV
        self._receipt = verify_mod.load_receipt(self._receipt_path)
        self.report = verify_mod.verify(self._composite_dir, self._receipt)
        self._render_report()
        self._render_status()

    # ── rendering ────────────────────────────────────────────────────────

    def _render_report(self) -> None:
        r = self.report
        head = f"Verify — baseline: {r.baseline_at or 'none (first deploy)'}"
        self.lines = [head]
        body = Text(head, style="bold")
        for c in r.checks:
            mark = "✓" if c.ok else "✗"
            line = f"{mark} {c.name}: {c.detail}"
            self.lines.append(line)
            body.append(f"\n{line}", style="green" if c.ok else "bold red")
        self.query_one("#deploy-report", Static).update(body)

    def _status_text(self) -> tuple[str, str]:
        if self.phase == "verify":
            if self.report.blocks_deploy and not self.overridden:
                return (
                    "✗ VERIFY FAILED — deploy blocked · [o] override (logged) · [esc] close",
                    "bold red",
                )
            if self.overridden:
                return "⚠ overridden — [d] dry-run deploy · [esc] close", "bold yellow"
            return "[d] dry-run deploy · [esc] close", "bold"
        if self.phase == "dry_running":
            return "dry-run in progress…", "yellow"
        if self.phase == "confirm":
            return "dry-run done — [a] APPLY TO PROD · [esc] cancel", "bold yellow"
        if self.phase == "applying":
            return "deploying… do not interrupt (sync in flight)", "bold yellow"
        if self.result_summary and self.result_summary.startswith("✓"):
            return f"{self.result_summary} · [esc] close", "bold green"
        return f"{self.result_summary or '✗ deploy failed'} · [esc] close", "bold white on red"

    def _render_status(self) -> None:
        text, style = self._status_text()
        self.status_line = text
        self.query_one("#deploy-status", Static).update(Text(text, style=style))

    def _append_output(self, line: str) -> None:
        self.output_lines.append(line)
        self.query_one("#deploy-output", Log).write_line(line)

    def _stream(self, step: str, line: str) -> None:
        """LineCallback for the driver — runs on the worker thread."""
        self.app.call_from_thread(self._append_output, f"[{step}] {line}")

    # ── phase actions ────────────────────────────────────────────────────

    def action_override(self) -> None:
        if self.phase != "verify" or not self.report.blocks_deploy or self.overridden:
            return
        self.overridden = True
        failed = ", ".join(c.name for c in self.report.checks if not c.ok)
        self.on_activity(f"verify override — deploying despite failed checks: {failed}", True)
        self._render_status()

    def action_dry_run(self) -> None:
        if self.phase != "verify" or (self.report.blocks_deploy and not self.overridden):
            return
        self.phase = "dry_running"
        self._render_status()
        self.run_worker(self._dry_worker, thread=True)

    def _dry_worker(self) -> None:
        result = deploy_mod.dry_run(self._script, self._stream)
        self.app.call_from_thread(self._dry_done, result)

    def _dry_done(self, result) -> None:
        if result.ok:
            self.phase = "confirm"
        else:
            self.phase = "done"
            self.result_summary = "✗ dry-run failed — deploy aborted"
            self._append_output(self.result_summary)
            self.on_activity("deploy dry-run failed", True)
        self._render_status()

    def action_apply(self) -> None:
        if self.phase != "confirm":
            return
        self.phase = "applying"
        self._render_status()
        # fresh is None only on an overridden unreadable-composite verify —
        # assume the owners index changed and restart to be safe.
        fresh = self.report.fresh
        restart_needed = fresh is None or deploy_mod.owners_changed(fresh["owners"], self._receipt)
        steps = deploy_mod.apply_steps(self._script, restart_needed, self._restart_argv)
        self.on_activity("deploy apply started — " + " → ".join(name for name, _ in steps), False)
        self.run_worker(lambda: self._apply_worker(steps), thread=True)

    def _apply_worker(self, steps) -> None:
        results = deploy_mod.run_apply(steps, self._stream)
        self.app.call_from_thread(self._apply_done, results)

    def _apply_done(self, results) -> None:
        self.phase = "done"
        if results and all(r.ok for r in results):
            self._append_output("✓ SMOKE PASSED")
            if self.report.fresh is not None:
                receipt = verify_mod.write_receipt(self.report.fresh, self._receipt_path)
                self._append_output(f"✓ deploy receipt written ({receipt['deployed_at']})")
            self.result_summary = "✓ deploy complete — smoke passed, receipt written"
            self.on_activity(self.result_summary, False)
            notify_send("morphy data: deploy complete", "Smoke passed; receipt written.")
        else:
            failed = results[-1]
            if failed.step == "smoke":
                banner = "✗✗✗ SMOKE FAILED — PROD MAY BE BROKEN ✗✗✗"
            else:
                banner = f"✗ deploy failed at '{failed.step}' — receipt NOT written"
            self._append_output(banner)
            self.result_summary = banner
            self.on_activity(banner, True)
            notify_send("morphy data: deploy FAILED", banner)
        self._render_status()

    def action_close(self) -> None:
        if self.phase in ("dry_running", "applying"):
            return  # a running leg must finish — never abandon a sync mid-flight
        self.dismiss(self.result_summary)
