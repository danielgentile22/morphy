"""``python -m app_puller`` entry point."""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``scripts/`` importable so the fetch package resolves whether the
# app is launched from the project root or via the .app bundle later.
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from app_puller.main_window import run  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run())
