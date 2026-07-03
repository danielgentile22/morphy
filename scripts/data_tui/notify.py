"""Desktop completion notifications via the platform notifier.

PRD #233 story 7: no notification dependency — macOS uses ``osascript``,
Linux uses ``notify-send`` when present, anything else is a silent no-op.
Best-effort by design: a notifier failure must never break the TUI.
Not a scheduler — fires only when an operator-triggered job ends, so
ADR-005 is untouched.
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def send(title: str, message: str) -> None:
    try:
        if sys.platform == "darwin":
            script = f'display notification "{_esc(message)}" with title "{_esc(title)}"'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", title, message], capture_output=True, timeout=5)
    except Exception:  # noqa: BLE001 — notification is never load-bearing
        pass
