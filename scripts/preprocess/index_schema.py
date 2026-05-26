"""Composite-index schema loader + validator.

The schema in ``schemas/index.schema.json`` is the single source of truth
for the ``composite/index.json`` contract — both the Python writer
(``app_assets.build_index``) and the TypeScript reader
(``app/src/lib/catalog.ts parseCompositeIndex``) must conform to it.

This module is a thin shim over ``typed_artifact``; the duplicated
lazy-import + lru-cache + path-prefixing logic now lives in one place.
Public names (`IndexSchemaViolation`, `validate_index`, `load_schema`)
are preserved so existing callers and tests don't need to change.
"""

from __future__ import annotations

from typing import Any

from .typed_artifact import (
    SCHEMAS_DIR,
    SchemaViolation,
    load_schema_file,
    validate_against_schema,
)

SCHEMA_FILENAME = "index.schema.json"
# Preserved for backwards-compat — legacy callers / tests imported this
# directly from this module.
SCHEMA_PATH = SCHEMAS_DIR / SCHEMA_FILENAME


class IndexSchemaViolation(SchemaViolation):
    """Raised when an index dict doesn't validate against index.schema.json."""


def load_schema() -> dict[str, Any]:
    """Read the index JSON Schema from disk (cached). Preserves the
    legacy public name; delegates to the shared loader."""
    return load_schema_file(SCHEMA_FILENAME)


def validate_index(index: dict[str, Any]) -> None:
    """Validate ``index`` against the schema. Raises IndexSchemaViolation
    on the first failure, with a path-prefixed message pointing at the
    bad field."""
    validate_against_schema(
        SCHEMA_FILENAME, index, IndexSchemaViolation, artifact_label="index.json"
    )
