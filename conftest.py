"""Pytest bootstrap.

The preprocess + fetch packages live under ``scripts/`` and are imported
as top-level packages (``import preprocess``), the same way
``scripts/preprocess.py`` bootstraps them. Put ``scripts/`` on
``sys.path`` so ``tests/`` can import them without an installed package.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
