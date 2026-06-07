"""Regression tests for the streaming Composer's per-chunk join applicators.

apply_county_score merges county distress values onto a parcel chunk that
already carries distress_tier / persistent_poverty placeholders (the
normalizer initialises them). It must use safe_merge so a raw merge's
_x/_y suffix collision doesn't drop the real columns — the bug that
blocked FL's recompose (KeyError 'distress_tier').
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from preprocess.annotators import county_score
from preprocess.per_chunk_joins import apply_county_score
from shapely.geometry import Point


def test_apply_county_score_overwrites_placeholders_without_suffix_collision():
    chunk = gpd.GeoDataFrame(
        {
            "county_fips": ["05001", "05001", "05003"],
            "distress_tier": ["", "", ""],  # normalizer placeholder
            "persistent_poverty": [False, False, False],  # normalizer placeholder
            "geometry": [Point(0, 0), Point(1, 1), Point(2, 2)],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )
    scores = pd.DataFrame(
        {
            "county_fips": ["05001", "05003"],
            "tier": ["distressed", "competitive"],
            "persistent_poverty": [True, False],
        }
    )
    # apply_county_score now takes an already-prepared rollup (PERF-021 hoists
    # county_score.prepare out of the shard loop); prepare it here.
    out = apply_county_score(chunk, county_score.prepare(scores))

    assert list(out["distress_tier"]) == ["distressed", "distressed", "competitive"]
    assert [bool(v) for v in out["persistent_poverty"]] == [True, True, False]
    # No leftover merge-suffix columns, and geometry typing preserved.
    assert not any(c.endswith(("_x", "_y", "_new")) for c in out.columns)
    assert isinstance(out, gpd.GeoDataFrame)


def test_apply_county_score_is_noop_without_scores():
    chunk = gpd.GeoDataFrame(
        {"county_fips": ["05001"], "geometry": [Point(0, 0)]},
        geometry="geometry",
        crs="EPSG:4326",
    )
    assert apply_county_score(chunk, None) is chunk
