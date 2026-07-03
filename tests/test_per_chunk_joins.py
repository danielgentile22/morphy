"""Regression tests for the chunked parcel-join seam (#263).

The county-score chunk stage merges county distress values onto a parcel
chunk that already carries distress_tier / persistent_poverty placeholders
(the normalizer initialises them). It must use safe_merge so a raw merge's
_x/_y suffix collision doesn't drop the real columns — the bug that
blocked FL's recompose (KeyError 'distress_tier'). Driven through the
registered CountyScoreToParcelJoin's prepare_chunks/apply_chunk — the seam
the Composer uses (ADR-002 / #263).
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import preprocess.registry  # noqa: F401 — populate the join registry
from preprocess.base import ComposeContext, all_joins
from shapely.geometry import Point


def _county_join():
    return next(j for j in all_joins() if j.name == "CountyScoreToParcelJoin")


def _ctx(scores: pd.DataFrame | None) -> ComposeContext:
    ctx = ComposeContext(state_fips="05", state_name="Arkansas", state_abbr="AR")
    if scores is not None:
        ctx.set("county_score", scores)
    return ctx


def test_county_chunk_stage_overwrites_placeholders_without_suffix_collision():
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
    join = _county_join()
    join.prepare_chunks(_ctx(scores))  # PERF-021 hoist lives here now
    out = join.apply_chunk(chunk)

    assert list(out["distress_tier"]) == ["distressed", "distressed", "competitive"]
    assert [bool(v) for v in out["persistent_poverty"]] == [True, True, False]
    # No leftover merge-suffix columns, and geometry typing preserved.
    assert not any(c.endswith(("_x", "_y", "_new")) for c in out.columns)
    assert isinstance(out, gpd.GeoDataFrame)


def test_county_chunk_stage_is_noop_without_scores():
    chunk = gpd.GeoDataFrame(
        {"county_fips": ["05001"], "geometry": [Point(0, 0)]},
        geometry="geometry",
        crs="EPSG:4326",
    )
    join = _county_join()
    join.prepare_chunks(_ctx(None))
    assert join.apply_chunk(chunk) is chunk
