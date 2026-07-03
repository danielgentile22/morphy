"""Tests for the parametric ``InfraToParcelJoin`` (#263 shape).

The single class registers three instances (tower / solar_facility /
billboard). Each instance *declares* the parcel columns to copy (with
renames) and the spatial predicate; the Composer's DuckDB pre-pass builds
the hits from those declarations (predicate semantics are pinned by the
PRD #135 equivalence harness), and ``apply()`` attaches the lookup onto
the infra layer. These tests pin the declarations, the attach behavior,
and the registrations.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from preprocess.base import ComposeContext, all_joins
from preprocess.joins.infra_to_parcel import (
    INFRA_PARCEL_RENAME,
    InfraToParcelJoin,
    apply_infra_lookup,
)
from shapely.geometry import Point


def _tower_join() -> InfraToParcelJoin:
    return InfraToParcelJoin(
        target_type="tower",
        name="TowerSeamTest",
        parcel_columns_map={
            "parcel_id_full": "parcel_id_full",
            "owner_name": "parcel_owner",
            "assessed_value": "parcel_value",
            "acreage": "parcel_acreage",
            "land_use_code": "parcel_use_code",
        },
    )


def test_apply_attaches_lookup_columns_onto_matched_rows():
    ctx = ComposeContext(state_fips="05", state_name="AR", state_abbr="AR")
    ctx.set(
        "tower",
        gpd.GeoDataFrame(
            {
                "asr_number": ["T001", "T002"],
                "owner_name": ["AT&T", "VERIZON"],
                "geometry": [Point(0.5, 0.5), Point(9, 9)],
            },
            crs="EPSG:4326",
        ),
    )
    join = _tower_join()
    # The pre-pass product: row index → renamed parcel columns (only T001 hit).
    ctx.artifacts[join.artifact_key()] = {
        0: {
            "parcel_id_full": "P001",
            "parcel_owner": "JANE OWNER",
            "parcel_value": 100_000.0,
            "parcel_use_code": "RES",
        }
    }
    join.apply(ctx)

    out = ctx.get("tower")
    assert out["parcel_id_full"][0] == "P001" and pd.isna(out["parcel_id_full"][1])
    assert out["parcel_owner"][0] == "JANE OWNER" and pd.isna(out["parcel_owner"][1])
    assert out["parcel_value"][0] == 100_000.0 and pd.isna(out["parcel_value"][1])
    assert "TowerSeamTest" in ctx.join_log


def test_apply_without_lookup_is_identity():
    ctx = ComposeContext(state_fips="05", state_name="AR", state_abbr="AR")
    tower = gpd.GeoDataFrame(
        {"asr_number": ["T1"], "geometry": [Point(0, 0)]},
        crs="EPSG:4326",
    )
    ctx.set("tower", tower)
    join = _tower_join()
    join.apply(ctx)  # no artifact stashed → empty lookup
    assert ctx.get("tower") is tower  # untouched, no phantom columns
    assert "parcel_id_full" not in ctx.get("tower").columns


def test_apply_infra_lookup_only_adds_columns_hits_provide():
    solar = gpd.GeoDataFrame(
        {"facility_id": ["S1", "S2"], "geometry": [Point(0, 0), Point(1, 1)]},
        crs="EPSG:4326",
    )
    out = apply_infra_lookup(solar, {1: {"parcel_id_full": "P9", "parcel_owner": "BOB"}})
    assert pd.isna(out["parcel_id_full"][0]) and out["parcel_id_full"][1] == "P9"
    assert pd.isna(out["parcel_owner"][0]) and out["parcel_owner"][1] == "BOB"
    assert "parcel_value" not in out.columns  # solar declares only id + owner


def test_declarations_are_the_single_source():
    """Predicates and keep-columns live on the registered instances — the
    pre-pass consumes exactly these (nothing re-declares them)."""
    from preprocess import registry  # noqa: F401

    by_name = {j.name: j for j in all_joins()}
    tower = by_name["TowerToParcelJoin"]
    solar = by_name["SolarToParcelJoin"]
    billboard = by_name["BillboardToParcelJoin"]
    assert tower.predicate == "within"
    # Solar may be polygons spanning multiple parcels — `intersects` is the
    # declared predicate so a partial overlap still attaches (audit M-a/#211).
    assert solar.predicate == "intersects"
    assert billboard.predicate == "within"
    assert list(tower.parcel_columns_map) == [
        "parcel_id_full",
        "owner_name",
        "assessed_value",
        "acreage",
        "land_use_code",
    ]
    assert set(solar.parcel_columns_map) == {"parcel_id_full", "owner_name"}
    # The rename union the pre-pass consumes comes from these declarations.
    assert INFRA_PARCEL_RENAME["owner_name"] == "parcel_owner"
    assert INFRA_PARCEL_RENAME["assessed_value"] == "parcel_value"


def test_three_instances_registered_under_legacy_names():
    """All three (tower / solar / billboard) instances must register so
    composer dependency resolution keeps working."""
    from preprocess import registry  # noqa: F401

    names = {j.name for j in all_joins()}
    assert {"TowerToParcelJoin", "SolarToParcelJoin", "BillboardToParcelJoin"} <= names
