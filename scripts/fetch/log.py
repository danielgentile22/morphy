"""Structured JSON-lines logger for the puller.

Each event is one JSON object written to ``data/fetch.log``. The UI
mirrors a friendlier version to its activity panel.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import LOG_PATH


def log_event(event: str, **fields: Any) -> None:
    """Append a single JSON object to fetch.log."""
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
    }
    payload.update(fields)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, default=str)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def tail(n: int = 200) -> list[dict[str, Any]]:
    """Return the last ``n`` events for the UI activity log."""
    if not LOG_PATH.exists():
        return []
    out: list[dict[str, Any]] = []
    with open(LOG_PATH, encoding="utf-8") as f:
        lines = f.readlines()[-n:]
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
