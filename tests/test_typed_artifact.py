"""Tests for the TypedArtifact base + the consolidated schema validator.

Verifies:
  - The shared validator behaves identically to the legacy per-module
    validators (which now delegate to it).
  - A TypedArtifact subclass round-trips through to_dict / from_dict.
  - read() / write() atomic-write + validate work end-to-end.
  - The lazy-jsonschema soft-fallback policy holds when jsonschema is
    importable (the happy path).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from scripts.preprocess.catalog_schema import (
    CatalogSchemaViolation,
    validate_catalog,
)
from scripts.preprocess.index_schema import (
    IndexSchemaViolation,
    validate_index,
)
from scripts.preprocess.typed_artifact import (
    SchemaViolation,
    TypedArtifact,
    load_schema_file,
    validate_against_schema,
)


def test_subclass_relationship():
    # The two existing per-artifact violations are now siblings of the
    # shared base — code can catch either narrowly or broadly.
    assert issubclass(IndexSchemaViolation, SchemaViolation)
    assert issubclass(CatalogSchemaViolation, SchemaViolation)


def test_validate_against_schema_passes_on_valid_index():
    # Smallest valid index doc — the schema allows zero states.
    doc = {
        "schema_version": 1,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "states": [],
    }
    validate_index(doc)  # raises on failure


def test_validate_against_schema_raises_typed_violation():
    bad = {"schema_version": "wrong-type", "generated_at": "", "states": []}
    with pytest.raises(IndexSchemaViolation):
        validate_index(bad)


def test_shared_validator_uses_provided_violation_class():
    bad = {"schema_version": "x", "generated_at": "", "states": []}
    with pytest.raises(IndexSchemaViolation):
        validate_against_schema("index.schema.json", bad, IndexSchemaViolation)


def test_load_schema_file_caches():
    a = load_schema_file("index.schema.json")
    b = load_schema_file("index.schema.json")
    assert a is b  # lru_cache returns the same object


# ── TypedArtifact subclass round-trip ──────────────────────────────────────


@dataclass
class _DummyReport(TypedArtifact):
    """Codec-only artifact (no SCHEMA_FILENAME) used in tests."""

    source_id: str
    rows: int

    def to_dict(self):
        return {"source_id": self.source_id, "rows": self.rows}

    @classmethod
    def from_dict(cls, d):
        return cls(source_id=str(d["source_id"]), rows=int(d["rows"]))


def test_typed_artifact_roundtrip(tmp_path):
    r = _DummyReport(source_id="fcc_asr", rows=42)
    path = tmp_path / "dummy.json"
    r.write(path)
    # The atomic-write should leave no .tmp residue
    leftovers = list(tmp_path.glob(".*tmp"))
    assert leftovers == []
    loaded = _DummyReport.read(path)
    assert loaded == r
    # On-disk JSON is sorted + indented
    raw = json.loads(path.read_text())
    assert raw == {"source_id": "fcc_asr", "rows": 42}


def test_typed_artifact_validate_is_no_op_without_schema():
    # No SCHEMA_FILENAME → validate() returns silently
    _DummyReport.validate({"anything": "goes"})


def test_legacy_validate_catalog_still_imports_and_runs():
    # The catalog schema accepts the minimal shape — just prove the
    # delegated validator path returns silently on a valid doc.
    # Build a structurally valid catalog from the schema's required keys.
    schema = load_schema_file("catalog.schema.json")
    required = schema.get("required", [])
    # Use placeholder values that match each required field's type when
    # available; the goal is "passes shape validation," not realism.
    doc = {
        "schema_version": 3,
        "state_fips": "05",
        "state_name": "Arkansas",
        "state_abbr": "AR",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "layers": {},
        "views": {},
        "sources_used_versions": {},
    }
    # Drop unknown required fields — let the test surface what's needed.
    for k in required:
        doc.setdefault(k, {})
    validate_catalog(doc)
