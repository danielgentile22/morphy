"""Preprocessing framework.

Reads from data/raw/<source_id>/current/ (the puller's output),
writes per-source canonical layers to data/processed/normalized/,
then composes per-state joined outputs to data/processed/composite/<state_fips>/.

See docs/ARCHITECTURE.md §3 for the framework architecture.
"""

from pathlib import Path

# Project paths — derived from this file's location.
PACKAGE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = SCRIPTS_DIR.parent
RAW_ROOT = PROJECT_ROOT / "data" / "raw"
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
NORMALIZED_ROOT = PROCESSED_ROOT / "normalized"
COMPOSITE_ROOT = PROCESSED_ROOT / "composite"
PREPROCESS_MANIFEST_PATH = PROCESSED_ROOT / "preprocess_manifest.json"
