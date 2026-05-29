"""Codec + JSON Schema validation primitives for typed artifacts.

Consolidates what was previously duplicated across several modules:
  - the lazy `jsonschema` import + soft-fallback policy (was open-coded
    in both `index_schema.py` and `catalog_schema.py`).
  - the lru-cached schema-file loader.
  - the `to_dict` / `from_dict` round-trip contract that
    `QualityReport`, `ManifestEntry`, etc. all implement individually.

Existing thin modules (`index_schema`, `catalog_schema`) now delegate to
the helpers here while preserving their public names — so external
imports and tests keep working unchanged.

Adding a new typed artifact (e.g. ADR-059's `LeaseExtraction`) is
one of two paths:

  1. Pure codec — subclass `TypedArtifact` and implement `to_dict` /
     `from_dict`. You get `read()` / `write()` (atomic write + optional
     schema validation) for free.

  2. JSON-Schema-validated artifact — also set `SCHEMA_FILENAME` and
     drop the schema in `scripts/preprocess/schemas/`. `validate()`
     picks it up automatically.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar

log = logging.getLogger("preprocess.typed_artifact")

SCHEMAS_DIR = Path(__file__).parent / "schemas"


class SchemaViolation(ValueError):
    """Raised when an artifact dict doesn't validate against its JSON Schema.

    Specific artifact modules subclass this so callers can catch a
    narrowly-scoped violation (e.g. `IndexSchemaViolation`) without
    losing the ability to catch the family with `SchemaViolation`.
    """


@lru_cache(maxsize=8)
def load_schema_file(filename: str) -> dict[str, Any]:
    """Read a JSON Schema from `schemas/<filename>` (cached)."""
    return json.loads((SCHEMAS_DIR / filename).read_text())


def validate_against_schema(
    schema_filename: str,
    document: dict[str, Any],
    violation_cls: type[SchemaViolation] = SchemaViolation,
    *,
    artifact_label: str | None = None,
) -> None:
    """Validate `document` against the JSON Schema in `schemas/<schema_filename>`.

    On a structural failure, raise `violation_cls` with a path-prefixed
    message pointing at the offending field. When `jsonschema` is not
    installed (production preprocess installs only runtime deps), log a
    warning and return — this is the same soft-fallback policy the two
    pre-existing validators had.
    """
    label = artifact_label or schema_filename
    try:
        import jsonschema  # type: ignore
    except ImportError:  # pragma: no cover — dev-deps always present in CI
        log.warning(
            "jsonschema not installed; skipping %s validation. "
            "Install requirements-dev.txt to enable strict checking.",
            label,
        )
        return

    schema = load_schema_file(schema_filename)
    try:
        jsonschema.validate(instance=document, schema=schema)
    except jsonschema.ValidationError as e:
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        raise violation_cls(
            f"{label} does not match {schema_filename} at {path}: {e.message}"
        ) from e


# ── TypedArtifact ABC ──────────────────────────────────────────────────────


class TypedArtifact(ABC):
    """Round-trip JSON + (optional) JSON Schema validation, in one place.

    Subclasses must implement `to_dict` and `from_dict`. Setting
    `SCHEMA_FILENAME` opts the class into validation in `read()` /
    `write()`; leaving it as None keeps those methods codec-only.

    Existing dataclasses already follow the to_dict/from_dict shape but
    don't currently subclass this — adopting it is mechanical and gets
    them atomic-write + validation hooks for free. New artifacts
    (e.g. Slice-4 LeaseExtraction) should subclass it directly.
    """

    SCHEMA_FILENAME: ClassVar[str | None] = None
    VIOLATION_CLS: ClassVar[type[SchemaViolation]] = SchemaViolation

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-serialisable dict."""

    @classmethod
    @abstractmethod
    def from_dict(cls, d: dict[str, Any]) -> TypedArtifact:
        """Parse a dict — tolerant of legacy / unknown keys."""

    @classmethod
    def validate(cls, document: dict[str, Any]) -> None:
        """Validate `document` against `SCHEMA_FILENAME`, if set."""
        if cls.SCHEMA_FILENAME is None:
            return
        validate_against_schema(
            cls.SCHEMA_FILENAME,
            document,
            cls.VIOLATION_CLS,
            artifact_label=cls.__name__,
        )

    @classmethod
    def read(cls, path: Path) -> TypedArtifact:
        """Read + parse from disk."""
        return cls.from_dict(json.loads(Path(path).read_text()))

    def write(self, path: Path) -> Path:
        """Atomic write: validate (if schema), then temp-file + rename.

        Mirrors the atomic-write pattern used elsewhere in the
        pipeline (e.g. `app_assets.write_composite_index`).
        """
        d = self.to_dict()
        type(self).validate(d)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(d, f, indent=2, sort_keys=True)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return path
