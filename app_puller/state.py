"""Persisted UI state for the puller.

Stored as JSON at ``~/.config/pilot/puller_state.json`` so the window
opens where the user left off (selected source, expanded categories,
log filter, window geometry).

State is best-effort — read/write errors are swallowed since UI state
is a nice-to-have, not load-bearing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "pilot"
STATE_PATH = CONFIG_DIR / "puller_state.json"


def load() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save(state: dict[str, Any]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=2, sort_keys=True)
    except OSError:
        pass
