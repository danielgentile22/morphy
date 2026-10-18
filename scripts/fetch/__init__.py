"""morphy data-fetch package.

Headless library that downloads, tracks, and validates every raw dataset
the project depends on. Consumed by the data TUI (`data_tui`) and
any future CLI driver.

Public surface:

    from fetch import registry, manifest
    sources = registry.all_sources()
    manifest.load()

Individual data sources live under ``fetch.sources`` and are registered
in ``fetch.registry``.
"""

from __future__ import annotations

from pathlib import Path

# Resolved at import time so every consumer agrees on where data lives.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifest.json"
LOG_PATH = PROJECT_ROOT / "data" / "fetch.log"

__all__ = ["PROJECT_ROOT", "RAW_ROOT", "MANIFEST_PATH", "LOG_PATH"]
