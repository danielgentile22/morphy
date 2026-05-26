"""Tests for the parametric CountyScoreLookupJoin.

Replaces what was implicit in the three deleted county_score_to_*.py
files. Verifies the same body annotates parcel / tower / solar_facility
correctly given the same county_score input.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

# Importing the registry ensures every Join is registered before the test
# touches the registry. The county-score lookup module registers three
# instances at import time.
from scripts.preprocess import registry  # noqa: F401
from scripts.preprocess.base import ComposeContext, all_joins
from scripts.preprocess.joins.county_score_lookup import (
    CountyScoreLookupJoin,
    _aggregate_county_score,
)


def _county_scores() -> pd.DataFrame:
    # Two sources contributing rows for the same county (ARC + USDA),
    # plus a third county with only USDA.
    return pd.DataFrame(
        [
            {"county_fips": "05001", "tier": "distressed", "persistent_poverty": True},
            {"county_fips": "05001", "tier": "", "persistent_poverty": True},
            {"county_fips": "05003", "tier": "at-risk", "persistent_poverty": False},
            {"county_fips": "30001", "tier": "", "persistent_poverty": False},
        ]
    )


def _parcels() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "parcel_id_full": ["A", "B", "C", "D"],
            "county_fips": ["05001", "05003", "30001", "99999"],
            "geometry": [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])] * 4,
        },
        geometry="geometry",
        crs="EPSG:4326",
    )


def _towers() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "asr_number": ["1", "2"],
            "county_fips": ["05001", "30001"],
            "geometry": [Point(0, 0), Point(1, 1)],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )


def _solar() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "facility_id": ["S1"],
            "county_fips": ["05001"],
            "geometry": [Point(0, 0)],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )


def _ctx_for(target_type: str):
    ctx = ComposeContext(state_fips="05", state_name="Arkansas", state_abbr="AR")
    if target_type == "parcel":
        ctx.set("parcel", _parcels())
    elif target_type == "tower":
        ctx.set("tower", _towers())
    elif target_type == "solar_facility":
        ctx.set("solar_facility", _solar())
    ctx.set("county_score", _county_scores())
    return ctx


def test_aggregate_county_score_collapses_multi_source_rows():
    agg = _aggregate_county_score(_county_scores())
    by_fips = {row.county_fips: row for row in agg.itertuples()}
    # ARC contributes "distressed" for 05001; USDA contributes "" — first
    # non-empty wins.
    assert by_fips["05001"].distress_tier == "distressed"
    # `any` over [True, True] → True for 05001
    assert by_fips["05001"].persistent_poverty is True
    assert by_fips["05003"].distress_tier == "at-risk"
    # USDA alone with empty tier — stays empty
    assert by_fips["30001"].distress_tier == ""


@pytest.mark.parametrize("target_type", ["parcel", "tower", "solar_facility"])
def test_county_score_lookup_annotates(target_type):
    ctx = _ctx_for(target_type)
    CountyScoreLookupJoin(target_type).apply(ctx)
    out = ctx.get(target_type)
    assert "distress_tier" in out.columns
    assert "persistent_poverty" in out.columns
    # County 05001 is "distressed" in the aggregate
    matched = out[out["county_fips"] == "05001"]
    assert (matched["distress_tier"] == "distressed").all()
    assert matched["persistent_poverty"].all()


def test_county_score_lookup_handles_missing_county_score():
    ctx = ComposeContext(state_fips="05", state_name="Arkansas", state_abbr="AR")
    ctx.set("parcel", _parcels())
    # No county_score table set — join should no-op without raising.
    CountyScoreLookupJoin("parcel").apply(ctx)
    out = ctx.get("parcel")
    # No annotation columns added
    assert "distress_tier" not in out.columns


def test_unmatched_county_gets_default_fillna():
    ctx = _ctx_for("parcel")
    CountyScoreLookupJoin("parcel").apply(ctx)
    out = ctx.get("parcel")
    # parcel D has county_fips 99999 — no county_score row
    row = out[out["parcel_id_full"] == "D"].iloc[0]
    assert row["distress_tier"] == ""
    assert row["persistent_poverty"] is False or row["persistent_poverty"] == False  # noqa: E712


def test_three_targets_registered_at_import_time():
    names = {j.name for j in all_joins()}
    assert "CountyScoreToParcelJoin" in names
    assert "CountyScoreToTowerJoin" in names
    # Solar pins the legacy name (no "Facility") so existing manifests
    # don't suddenly see a renamed join.
    assert "CountyScoreToSolarJoin" in names
