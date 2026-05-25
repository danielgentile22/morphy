"""Composite-index schema loader + validator.

The schema in ``schemas/index.schema.json`` is the single source of truth
for the ``composite/index.json`` contract — both the Python writer
(``app_assets.build_index``) and the TypeScript reader
(``app/src/lib/catalog.ts parseCompositeIndex``) must conform to it.

Mirrors ``catalog_schema.py`` in shape — see that module's docstring for
the rationale on lazy ``jsonschema`` import + soft fallback behavior.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).parent / "schemas" / "index.schema.json"


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Read the index JSON Schema from disk (cached)."""
    return json.loads(SCHEMA_PATH.read_text())


class IndexSchemaViolation(ValueError):
    """Raised when an index dict doesn't validate against index.schema.json."""


def validate_index(index: dict[str, Any]) -> None:
    """Validate ``index`` against the schema. Raises IndexSchemaViolation
    on the first failure, with a path-prefixed message pointing at the
    bad field.
    """
    try:
        import jsonschema
    except ImportError:  # pragma: no cover — dev-deps are always present in CI
        import logging

        logging.getLogger("preprocess.app_assets").warning(
            "jsonschema not installed; skipping index schema validation. "
            "Install requirements-dev.txt to enable strict checking."
        )
        return

    schema = load_schema()
    try:
        jsonschema.validate(instance=index, schema=schema)
    except jsonschema.ValidationError as e:
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        raise IndexSchemaViolation(
            f"index.json does not match index.schema.json at {path}: {e.message}"
        ) from e
