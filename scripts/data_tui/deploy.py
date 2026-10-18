"""Deploy driver (#239) — wraps deploy.sh's data/smoke legs + the app restart.

Data deploys only (shipping the app image stays a dev workflow). The
driver encodes the prod-ops sequencing that used to live in memory:
the restart runs strictly *after* the sync leg exits (never mid-sync —
a restart kills leg 2's rclone and leaves the volume partial) and only
when the owners index changed (the backend caches it at startup), then
smoke checks the restarted app. Output streams line-by-line so the TUI
can show a live deploy.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from fetch import PROJECT_ROOT

DEPLOY_SCRIPT = PROJECT_ROOT / "deploy.sh"
FLY_APP = os.environ.get("FLY_APP", "morphy-demo")  # deploy.sh's own default
RESTART_ARGV = ("fly", "apps", "restart", FLY_APP)

LineCallback = Callable[[str, str], None]  # (step name, output line)


@dataclass(frozen=True)
class StepResult:
    step: str
    returncode: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def owners_changed(fresh_owners: dict, receipt: dict | None) -> bool:
    """Restart needed: the backend caches owners_index.json at startup, so a
    changed index reports owners_indexed=0 until the app restarts."""
    return receipt is None or fresh_owners != receipt.get("owners")


def apply_steps(
    script: str | os.PathLike,
    restart_needed: bool,
    restart_argv: tuple[str, ...] = RESTART_ARGV,
) -> list[tuple[str, tuple[str, ...]]]:
    """Ordered (name, argv) steps: sync → restart (if owners changed) → smoke."""
    steps = [("sync", (str(script), "data", "--apply"))]
    if restart_needed:
        steps.append(("restart", tuple(restart_argv)))
    steps.append(("smoke", (str(script), "smoke")))
    return steps


def run_step(step: str, argv: tuple[str, ...], on_line: LineCallback) -> StepResult:
    proc = subprocess.Popen(list(argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    for line in proc.stdout:
        on_line(step, line.rstrip("\n"))
    return StepResult(step, proc.wait())


def dry_run(script: str | os.PathLike, on_line: LineCallback) -> StepResult:
    """deploy.sh data with no --apply — its default is a dry-run that reports
    what would transfer without writing."""
    return run_step("dry-run", (str(script), "data"), on_line)


def run_apply(steps: list[tuple[str, tuple[str, ...]]], on_line: LineCallback) -> list[StepResult]:
    """Run steps in order, stopping at the first failure — a failed sync must
    never be followed by a restart or smoke against a half-synced volume."""
    results: list[StepResult] = []
    for step, argv in steps:
        result = run_step(step, argv, on_line)
        results.append(result)
        if not result.ok:
            break
    return results
