"""Tests for the catalog.json schema contract.

The schema in ``scripts/preprocess/schemas/catalog.schema.json`` is the
single source of truth for the Python ↔ TypeScript catalog contract.
These tests assert:

- The schema itself loads and is a valid JSON Schema.
- The committed golden fixture validates against the schema.
- A synthetic ``_build_catalog`` run produces a dict that validates.
- Targeted mutations (missing required field, wrong type, wrong
  schema_version) fail loudly with a useful error path.

The matching TS-side test is ``app/tests/unit/catalog-contract.test.ts``;
both consume the same golden fixture under ``tests/fixtures/catalog/``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from preprocess.base import ComposeContext
from preprocess.catalog_schema import (
    SCHEMA_PATH,
    CatalogSchemaViolation,
    load_schema,
    validate_catalog,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "catalog" / "golden_catalog.json"


@pytest.fixture
def golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text())


# ── schema sanity ────────────────────────────────────────────────────────


def test_schema_file_exists_at_known_path():
    """Anchor the schema location — both this test and the TS test rely on it."""
    assert SCHEMA_PATH.exists()
    assert SCHEMA_PATH.name == "catalog.schema.json"


def test_schema_loads_and_pins_version_to_3():
    schema = load_schema()
    assert schema["properties"]["schema_version"]["const"] == 3


# ── golden fixture ───────────────────────────────────────────────────────


def test_golden_fixture_validates(golden):
    """The committed golden_catalog.json is itself a valid catalog."""
    validate_catalog(golden)  # raises on failure


def test_golden_has_one_of_each_layer_kind(golden):
    """Sanity: the golden exercises every interesting layer/view shape so
    the TS-side test has full coverage from one file."""
    # Layer with geojson_path (towers), one with simplified_geojson_path
    # (parcels), one tabular (county_scores).
    assert "towers" in golden["layers"]
    assert "parcels" in golden["layers"]
    assert "county_scores" in golden["layers"]
    assert "geojson_path" in golden["layers"]["towers"]
    assert "simplified_geojson_path" in golden["layers"]["parcels"]
    assert "geometry_type" not in golden["layers"]["county_scores"]

    # Spatial view (LLC view) + tabular view (owner_clusters with
    # geometry_type=null).
    assert "llc_owned_parcels_with_infra" in golden["views"]
    assert golden["views"]["llc_owned_parcels_with_infra"]["geometry_type"] == "Polygon"
    assert golden["views"]["owner_clusters"]["geometry_type"] is None


# ── violations are loud ──────────────────────────────────────────────────


def test_missing_required_field_raises(golden):
    bad = {**golden}
    del bad["state_fips"]
    with pytest.raises(CatalogSchemaViolation) as exc:
        validate_catalog(bad)
    assert "state_fips" in str(exc.value) or "required" in str(exc.value)


def test_wrong_schema_version_raises(golden):
    bad = {**golden, "schema_version": 99}
    with pytest.raises(CatalogSchemaViolation) as exc:
        validate_catalog(bad)
    assert "schema_version" in str(exc.value).lower() or "/schema_version" in str(exc.value)


def test_unexpected_top_level_field_raises(golden):
    """`additionalProperties: false` catches stray fields. Critical for
    drift detection — a Python-side rename would otherwise add a new
    field silently."""
    bad = {**golden, "unexpected_field": "oops"}
    with pytest.raises(CatalogSchemaViolation):
        validate_catalog(bad)


def test_layer_missing_required_field_raises(golden):
    bad = json.loads(json.dumps(golden))  # deep copy
    del bad["layers"]["towers"]["canonical_type"]
    with pytest.raises(CatalogSchemaViolation) as exc:
        validate_catalog(bad)
    # Error path should mention layers/towers — the user can find the bad row.
    msg = str(exc.value)
    assert "layers" in msg and "towers" in msg


def test_view_geometry_type_must_be_string_or_null(golden):
    bad = json.loads(json.dumps(golden))
    bad["views"]["llc_owned_parcels_with_infra"]["geometry_type"] = 123
    with pytest.raises(CatalogSchemaViolation):
        validate_catalog(bad)


# ── round-trip: _build_catalog output validates ──────────────────────────


def test_build_catalog_output_validates_against_schema(monkeypatch):
    """The Python writer's output must satisfy the contract — this is the
    drift-detection mechanism. If _build_catalog adds/removes a field
    without updating the schema, this test fails."""
    from preprocess import compose
    from preprocess.geographies import get_state

    state = get_state("05")
    ctx = ComposeContext(state_fips=state.fips, state_name=state.name, state_abbr=state.abbr)

    # Seed one tiny synthetic layer so layers isn't empty.
    ctx.tables["county_score"] = pd.DataFrame(
        [{"county_fips": "05001", "state_fips": "05", "tier": "distressed"}]
    )

    # _build_catalog calls get_raw_local_version per source; with no real
    # manifest present that returns None — patch to keep the test
    # hermetic and avoid touching data/.
    monkeypatch.setattr(compose, "get_raw_local_version", lambda _sid: "test-vintage")

    catalog = compose._build_catalog(
        state=state,
        ctx=ctx,
        view_meta={},
        out_dir=Path("/tmp/nonexistent-for-this-test"),
        sources_used=["usda_persistent_poverty"],
    )

    validate_catalog(catalog)  # raises on schema drift
    assert catalog["schema_version"] == 3
    assert catalog["state_fips"] == "05"
    assert "county_scores" in catalog["layers"]
