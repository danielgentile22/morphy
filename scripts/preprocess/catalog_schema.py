"""Catalog schema loader + validator.

The schema in ``schemas/catalog.schema.json`` is the single source of truth
for the per-state ``composite/<fips>/catalog.json`` contract — both the
Python writer (``compose._build_catalog``) and the TypeScript reader
(``app/src/lib/catalog.ts parseCatalog``) must conform to it.

The Python side enforces the contract at write time: ``validate_catalog``
raises on any drift before the file hits disk. The TypeScript side
enforces it at parse time (hand-written, see ``catalog.ts``); the shared
golden fixture under ``tests/fixtures/catalog/`` is the round-trip
evidence that both sides agree.

``jsonschema`` is a dev-time dependency only (``requirements-dev.txt``);
``compose.py`` imports lazily so production preprocess runs without
``jsonschema`` installed will skip validation rather than crash. The
warning is loud — install dev deps to re-enable strict checking.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).parent / "schemas" / "catalog.schema.json"


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Read the catalog JSON Schema from disk (cached)."""
    return json.loads(SCHEMA_PATH.read_text())


class CatalogSchemaViolation(ValueError):
    """Raised when a catalog dict doesn't validate against catalog.schema.json."""


def validate_catalog(catalog: dict[str, Any]) -> None:
    """Validate ``catalog`` against the schema. Raises CatalogSchemaViolation
    on the first failure, with a path-prefixed message pointing at the bad
    field.

    Importing ``jsonschema`` is deferred to keep ``compose`` runnable in
    environments where dev deps aren't installed — there, validation
    skips with a warning. Production preprocess runs are dev-deps-only
    in practice, so this is a soft fallback.
    """
    try:
        import jsonschema
    except ImportError:  # pragma: no cover — dev-deps are always present in CI
        import logging

        logging.getLogger("preprocess.compose").warning(
            "jsonschema not installed; skipping catalog schema validation. "
            "Install requirements-dev.txt to enable strict checking."
        )
        return

    schema = load_schema()
    try:
        jsonschema.validate(instance=catalog, schema=schema)
    except jsonschema.ValidationError as e:
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        raise CatalogSchemaViolation(
            f"catalog.json does not match catalog.schema.json at {path}: {e.message}"
        ) from e
