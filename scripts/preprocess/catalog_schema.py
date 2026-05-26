"""Catalog schema loader + validator.

The schema in ``schemas/catalog.schema.json`` is the single source of truth
for the per-state ``composite/<fips>/catalog.json`` contract — both the
Python writer (``compose._build_catalog``) and the TypeScript reader
(``app/src/lib/catalog.ts parseCatalog``) must conform to it.

This module is a thin shim over ``typed_artifact``; the duplicated
lazy-import + lru-cache + path-prefixing logic now lives in one place.
Public names (`CatalogSchemaViolation`, `validate_catalog`, `load_schema`)
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

SCHEMA_FILENAME = "catalog.schema.json"
# Preserved for backwards-compat — legacy callers / tests imported this
# directly from this module.
SCHEMA_PATH = SCHEMAS_DIR / SCHEMA_FILENAME


class CatalogSchemaViolation(SchemaViolation):
    """Raised when a catalog dict doesn't validate against catalog.schema.json."""


def load_schema() -> dict[str, Any]:
    """Read the catalog JSON Schema from disk (cached). Preserves the
    legacy public name; delegates to the shared loader."""
    return load_schema_file(SCHEMA_FILENAME)


def validate_catalog(catalog: dict[str, Any]) -> None:
    """Validate ``catalog`` against the schema. Raises CatalogSchemaViolation
    on the first failure, with a path-prefixed message pointing at the
    bad field."""
    validate_against_schema(
        SCHEMA_FILENAME, catalog, CatalogSchemaViolation, artifact_label="catalog.json"
    )
