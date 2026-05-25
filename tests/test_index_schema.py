"""Tests for the index.json schema contract.

The schema in ``scripts/preprocess/schemas/index.schema.json`` is the
single source of truth for the Python ↔ TypeScript composite-index
contract. These tests assert:

- The schema itself loads with the expected version pin.
- The committed golden fixture validates.
- A synthetic ``build_index`` run produces a dict that validates.
- Targeted mutations fail loudly with a useful error path.

The matching TS-side test is ``app/tests/unit/index-contract.test.ts``;
both consume ``tests/fixtures/catalog/golden_index.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from preprocess.index_schema import (
    SCHEMA_PATH,
    IndexSchemaViolation,
    load_schema,
    validate_index,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "catalog" / "golden_index.json"


@pytest.fixture
def golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text())


# ── schema sanity ────────────────────────────────────────────────────────


def test_schema_file_exists_at_known_path():
    assert SCHEMA_PATH.exists()
    assert SCHEMA_PATH.name == "index.schema.json"


def test_schema_pins_version_to_1():
    schema = load_schema()
    assert schema["properties"]["schema_version"]["const"] == 1


# ── golden fixture ───────────────────────────────────────────────────────


def test_golden_fixture_validates(golden):
    validate_index(golden)  # raises on failure


def test_golden_exercises_each_state_shape(golden):
    """Sanity check the fixture so the TS test inherits broad coverage."""
    states = {s["fips"]: s for s in golden["states"]}
    # AR has multi-canonical counts
    assert "tower" in states["05"]["counts"] and "county_score" in states["05"]["counts"]
    # MT has a smaller counts set
    assert states["30"]["counts"] == {"parcel": 920111, "tower": 642}
    # FL has empty counts (state composed but no rows yet)
    assert states["12"]["counts"] == {}


# ── violations are loud ──────────────────────────────────────────────────


def test_missing_required_root_field_raises(golden):
    bad = {**golden}
    del bad["states"]
    with pytest.raises(IndexSchemaViolation) as exc:
        validate_index(bad)
    assert "states" in str(exc.value) or "required" in str(exc.value)


def test_wrong_schema_version_raises(golden):
    bad = {**golden, "schema_version": 99}
    with pytest.raises(IndexSchemaViolation) as exc:
        validate_index(bad)
    assert "schema_version" in str(exc.value).lower() or "/schema_version" in str(exc.value)


def test_unexpected_top_level_field_raises(golden):
    bad = {**golden, "unexpected_field": "oops"}
    with pytest.raises(IndexSchemaViolation):
        validate_index(bad)


def test_state_missing_required_field_raises(golden):
    bad = json.loads(json.dumps(golden))  # deep copy
    del bad["states"][0]["abbr"]
    with pytest.raises(IndexSchemaViolation) as exc:
        validate_index(bad)
    assert "states" in str(exc.value)


def test_bbox_must_have_exactly_four_numbers(golden):
    bad = json.loads(json.dumps(golden))
    bad["states"][0]["bbox"] = [-94.62, 33.0, -89.64]  # only 3
    with pytest.raises(IndexSchemaViolation):
        validate_index(bad)


def test_state_fips_must_be_two_chars(golden):
    bad = json.loads(json.dumps(golden))
    bad["states"][0]["fips"] = "5"  # not 2 chars
    with pytest.raises(IndexSchemaViolation):
        validate_index(bad)


def test_counts_value_must_be_integer(golden):
    bad = json.loads(json.dumps(golden))
    bad["states"][0]["counts"]["parcel"] = "not a number"
    with pytest.raises(IndexSchemaViolation):
        validate_index(bad)


# ── round-trip: build_index output validates ────────────────────────────


def test_build_index_output_validates_against_schema(tmp_path):
    """The Python writer's output must satisfy the contract."""
    from preprocess.app_assets import build_index

    # Build a fake composite/ with one valid state directory.
    fips = "05"
    sdir = tmp_path / fips
    sdir.mkdir()
    (sdir / "catalog.json").write_text("{}")  # presence-check only
    (sdir / "summary.json").write_text(json.dumps({"counts": {"parcel": 100}}))

    index = build_index(tmp_path)
    validate_index(index)  # raises on schema drift
    assert index["schema_version"] == 1
    assert len(index["states"]) == 1
    assert index["states"][0]["fips"] == "05"
    assert index["states"][0]["counts"] == {"parcel": 100}


def test_build_index_empty_root_still_validates(tmp_path):
    """An empty composite/ should still produce a schema-valid index
    (zero states, but the envelope is still valid)."""
    from preprocess.app_assets import build_index

    index = build_index(tmp_path)
    validate_index(index)
    assert index["states"] == []
