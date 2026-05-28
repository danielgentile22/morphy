"""Tests for the parametric SpatialAttributeJoin.

Replaces what was implicit in the two deleted ParcelToDistress /
TowerToDistress files: the same template body annotates two target
types with the same overlay-derived columns under different predicates.
"""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import Point, Polygon

# Force registration of every Join.
from preprocess import registry  # noqa: F401
from preprocess.base import ComposeContext, all_joins
from preprocess.joins.spatial_attribute import (
    PARCEL_TO_DISTRESS_SPEC,
    TOWER_TO_DISTRESS_SPEC,
    SpatialAttributeJoin,
    SpatialAttributeSpec,
)


def _distress_overlays() -> gpd.GeoDataFrame:
    # Two overlay types covering different regions
    oz = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    qct = Polygon([(1, 1), (3, 1), (3, 3), (1, 3)])
    return gpd.GeoDataFrame(
        {
            "overlay_type": ["opportunity_zone", "qct"],
            "geometry": [oz, qct],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )


def _parcels() -> gpd.GeoDataFrame:
    # A: only in OZ; B: in both; C: in neither
    return gpd.GeoDataFrame(
        {
            "parcel_id_full": ["A", "B", "C"],
            "geometry": [
                Polygon([(0.1, 0.1), (0.5, 0.1), (0.5, 0.5), (0.1, 0.5)]),
                Polygon([(1.2, 1.2), (1.8, 1.2), (1.8, 1.8), (1.2, 1.8)]),
                Polygon([(4, 4), (5, 4), (5, 5), (4, 5)]),
            ],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )


def _towers() -> gpd.GeoDataFrame:
    # T1: inside OZ only; T2: inside both; T3: inside neither
    return gpd.GeoDataFrame(
        {
            "asr_number": ["T1", "T2", "T3"],
            "geometry": [Point(0.5, 0.5), Point(1.5, 1.5), Point(4.5, 4.5)],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )


def _ctx(target_type: str, target_gdf):
    ctx = ComposeContext(state_fips="05", state_name="AR", state_abbr="AR")
    ctx.set(target_type, target_gdf)
    ctx.set("distress_overlay", _distress_overlays())
    return ctx


def test_parcel_distress_annotation_uses_intersects():
    ctx = _ctx("parcel", _parcels())
    SpatialAttributeJoin(PARCEL_TO_DISTRESS_SPEC, "ParcelToDistressJoin").apply(ctx)
    out = ctx.get("parcel").set_index("parcel_id_full")

    assert out.loc["A", "in_oz"] is True or out.loc["A", "in_oz"] == True  # noqa: E712
    assert out.loc["A", "in_qct"] is False or out.loc["A", "in_qct"] == False  # noqa: E712
    assert out.loc["B", "in_oz"]
    assert out.loc["B", "in_qct"]
    assert not out.loc["C", "in_oz"]
    assert not out.loc["C", "in_qct"]
    assert out.loc["B", "distress_overlays"] == ["opportunity_zone", "qct"]
    assert out.loc["C", "distress_overlays"] == []


def test_tower_distress_annotation_uses_within():
    ctx = _ctx("tower", _towers())
    SpatialAttributeJoin(TOWER_TO_DISTRESS_SPEC, "TowerToDistressJoin").apply(ctx)
    out = ctx.get("tower").set_index("asr_number")

    assert out.loc["T1", "in_oz"]
    assert not out.loc["T1", "in_qct"]
    assert out.loc["T2", "in_oz"]
    assert out.loc["T2", "in_qct"]
    assert not out.loc["T3", "in_oz"]
    assert not out.loc["T3", "in_qct"]


def test_missing_source_no_ops():
    ctx = ComposeContext(state_fips="05", state_name="AR", state_abbr="AR")
    ctx.set("parcel", _parcels())
    SpatialAttributeJoin(PARCEL_TO_DISTRESS_SPEC, "ParcelToDistressJoin").apply(ctx)
    out = ctx.get("parcel")
    # No annotation columns added when distress_overlay isn't present
    assert "in_oz" not in out.columns


def test_legacy_join_names_still_registered():
    names = {j.name for j in all_joins()}
    assert "ParcelToDistressJoin" in names
    assert "TowerToDistressJoin" in names


@pytest.mark.parametrize(
    "spec_name", ["ParcelToDistressJoin", "TowerToDistressJoin"]
)
def test_columns_added_match_derived_keys(spec_name):
    joins = {j.name: j for j in all_joins()}
    j = joins[spec_name]
    assert set(j.columns_added) == {"distress_overlays", "in_oz", "in_qct"}


def test_template_handles_a_brand_new_spec():
    """Future use case: a single-derived-column annotation."""
    spec = SpatialAttributeSpec(
        target="parcel",
        source="distress_overlay",
        predicate="intersects",
        category_column="overlay_type",
        derived_columns={"any_overlay": lambda s: len(s) > 0},
    )
    ctx = _ctx("parcel", _parcels())
    SpatialAttributeJoin(spec, "AnyOverlayJoin").apply(ctx)
    out = ctx.get("parcel").set_index("parcel_id_full")
    assert out.loc["A", "any_overlay"]
    assert out.loc["B", "any_overlay"]
    assert not out.loc["C", "any_overlay"]
