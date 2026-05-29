"""Tests for the parametric ``InfraToParcelJoin``.

The single class registers three instances (tower / solar_facility /
billboard). Each instance copies a different set of parcel columns
onto the infra row via sjoin. These tests assert the parametric form
behaves identically per kind and that the registry holds all three
under their legacy names.
"""

from __future__ import annotations

import geopandas as gpd
import pytest
from preprocess.base import ComposeContext, all_joins
from preprocess.joins.infra_to_parcel import InfraToParcelJoin
from shapely.geometry import Point, Polygon


def _parcel_gdf():
    return gpd.GeoDataFrame(
        {
            "parcel_id_full": ["P001", "P002"],
            "owner_name": ["JANE OWNER", "BOB OWNER"],
            "assessed_value": [100_000.0, 200_000.0],
            "acreage": [1.5, 3.0],
            "land_use_code": ["RES", "AGR"],
            "geometry": [
                Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                Polygon([(2, 0), (3, 0), (3, 1), (2, 1)]),
            ],
        },
        crs="EPSG:4326",
    )


def test_tower_join_copies_all_parcel_cols():
    ctx = ComposeContext(state_fips="05", state_name="AR", state_abbr="AR")
    ctx.set("parcel", _parcel_gdf())
    ctx.set(
        "tower",
        gpd.GeoDataFrame(
            {
                "asr_number": ["T001"],
                "owner_name": ["AT&T"],
                "geometry": [Point(0.5, 0.5)],
            },
            crs="EPSG:4326",
        ),
    )

    join = InfraToParcelJoin(
        target_type="tower",
        name="TowerToParcelJoin",
        parcel_columns_map={
            "parcel_id_full": "parcel_id_full",
            "owner_name": "parcel_owner",
            "assessed_value": "parcel_value",
            "acreage": "parcel_acreage",
            "land_use_code": "parcel_use_code",
        },
    )
    join.apply(ctx)

    out = ctx.get("tower")
    assert list(out["parcel_id_full"]) == ["P001"]
    assert list(out["parcel_owner"]) == ["JANE OWNER"]
    assert list(out["parcel_value"]) == [100_000.0]
    assert list(out["parcel_use_code"]) == ["RES"]
    # The right-side index-prefix that sjoin emits must be dropped.
    assert not any(c.startswith("index_right") for c in out.columns)
    assert "TowerToParcelJoin" in ctx.join_log


def test_billboard_join_only_copies_id_and_owner():
    ctx = ComposeContext(state_fips="05", state_name="AR", state_abbr="AR")
    ctx.set("parcel", _parcel_gdf())
    ctx.set(
        "billboard",
        gpd.GeoDataFrame(
            {
                "permit_no": ["BB-1"],
                "owner": ["Outfront"],
                "geometry": [Point(2.5, 0.5)],
            },
            crs="EPSG:4326",
        ),
    )

    join = InfraToParcelJoin(
        target_type="billboard",
        name="BillboardToParcelJoin",
        parcel_columns_map={
            "parcel_id_full": "parcel_id_full",
            "owner_name": "parcel_owner",
        },
    )
    join.apply(ctx)

    out = ctx.get("billboard")
    assert list(out["parcel_id_full"]) == ["P002"]
    assert list(out["parcel_owner"]) == ["BOB OWNER"]
    # parcel_value / acreage / use_code should NOT have been copied.
    assert "parcel_value" not in out.columns
    assert "parcel_acreage" not in out.columns


def test_solar_join_uses_intersects_predicate():
    """Solar may be polygons spanning multiple parcels — `intersects`
    is the right predicate so a partial overlap still attaches."""
    ctx = ComposeContext(state_fips="05", state_name="AR", state_abbr="AR")
    ctx.set("parcel", _parcel_gdf())
    # Solar polygon overlaps the edge of P001 (within would miss; intersects hits)
    ctx.set(
        "solar_facility",
        gpd.GeoDataFrame(
            {
                "facility_id": ["S-1"],
                "operator": ["SolarCo"],
                "geometry": [Polygon([(-0.5, 0.4), (0.5, 0.4), (0.5, 0.6), (-0.5, 0.6)])],
            },
            crs="EPSG:4326",
        ),
    )

    join = InfraToParcelJoin(
        target_type="solar_facility",
        name="SolarToParcelJoin",
        parcel_columns_map={
            "parcel_id_full": "parcel_id_full",
            "owner_name": "parcel_owner",
        },
        predicate="intersects",
    )
    join.apply(ctx)

    out = ctx.get("solar_facility")
    # P001's western edge is at x=0; the polygon extends from -0.5 to 0.5,
    # so they intersect.
    assert list(out["parcel_id_full"]) == ["P001"]


def test_three_instances_registered_under_legacy_names():
    """All three (tower / solar / billboard) instances must register so
    composer dependency resolution keeps working."""
    # Force registry to populate.
    from preprocess import registry  # noqa: F401

    names = {j.name for j in all_joins()}
    assert {"TowerToParcelJoin", "SolarToParcelJoin", "BillboardToParcelJoin"} <= names


def test_missing_geometry_is_no_op():
    ctx = ComposeContext(state_fips="05", state_name="AR", state_abbr="AR")
    # Parcels with no geometry column → join must not crash; it leaves
    # the infra table untouched.
    ctx.set("parcel", gpd.GeoDataFrame({"parcel_id_full": ["P1"]}))
    ctx.set(
        "tower",
        gpd.GeoDataFrame(
            {"asr_number": ["T1"], "geometry": [Point(0, 0)]},
            crs="EPSG:4326",
        ),
    )
    join = InfraToParcelJoin(
        target_type="tower",
        name="TowerToParcelJoin",
        parcel_columns_map={"parcel_id_full": "parcel_id_full"},
    )
    join.apply(ctx)
    out = ctx.get("tower")
    # No parcel column copied since the parcel table had no geometry.
    assert "parcel_id_full" not in out.columns or list(out["parcel_id_full"]) == ["T1"]
