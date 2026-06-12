"""``python -m app_puller`` entry point.

The ``fetch`` package (and the scripts/ top-level modules) resolve via the
editable install that ``uv sync`` performs — no path bootstrapping here.
"""

from __future__ import annotations

from app_puller.main_window import run

if __name__ == "__main__":
    raise SystemExit(run())
