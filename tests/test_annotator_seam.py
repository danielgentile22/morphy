"""Seam tests: the whole-layer feed and the per-chunk feed are one body.

These prove the deepening goal — each parcel annotation is computed in
exactly one place, fed two ways — by driving the *real* entry points
(the registered Join for the whole-layer feed, the
``preprocess.per_chunk_joins`` adapter for the streaming feed) over the
same toy parcels and asserting identical annotation columns. If the two
feeds ever drift, these go red.

owner-cluster's feed-agnosticism is pinned in test_owner_cluster_join.py
(``test_prepare_is_feed_agnostic``).
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

# Force registration of every Join.
from preprocess import registry  # noqa: F401
from preprocess.base import ComposeContext
from preprocess.joins.county_score_lookup import CountyScoreLookupJoin
from preprocess.joins.spatial_attribute import PARCEL_TO_DISTRESS_SPEC, SpatialAttributeJoin
from preprocess.per_chunk_joins import apply_county_score, apply_parcel_to_distress
from shapely.geometry import Polygon


def _parcels() -> gpd.GeoDataFrame:
    # Four valid parcels spread across three counties; geometry overlaps an
    # OZ / QCT region so the distress feed has something to bucket.
    polys = [
        Polygon([(0.1, 0.1), (0.5, 0.1), (0.5, 0.5), (0.1, 0.5)]),  # in OZ only
        Polygon([(1.2, 1.2), (1.8, 1.2), (1.8, 1.8), (1.2, 1.8)]),  # in OZ + QCT
        Polygon([(4.0, 4.0), (5.0, 4.0), (5.0, 5.0), (4.0, 5.0)]),  # in neither
        Polygon([(0.2, 0.2), (0.4, 0.2), (0.4, 0.4), (0.2, 0.4)]),  # in OZ only
    ]
    return gpd.GeoDataFrame(
        {
            "parcel_id_full": ["A", "B", "C", "D"],
            "county_fips": ["05001", "05003", "30001", "05001"],
            # Normalizer placeholders the annotators must overwrite cleanly.
            "distress_tier": ["", "", "", ""],
            "persistent_poverty": [False, False, False, False],
            "distress_overlays": [[], [], [], []],
            "in_oz": [False, False, False, False],
            "in_qct": [False, False, False, False],
            "geometry": polys,
        },
        geometry="geometry",
        crs="EPSG:4326",
    )


def _scores() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"county_fips": "05001", "tier": "distressed", "persistent_poverty": True},
            {"county_fips": "05001", "tier": "", "persistent_poverty": True},  # 2nd source
            {"county_fips": "05003", "tier": "at-risk", "persistent_poverty": False},
        ]
    )


def _overlays() -> gpd.GeoDataFrame:
    oz = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    qct = Polygon([(1, 1), (3, 1), (3, 3), (1, 3)])
    return gpd.GeoDataFrame(
        {"overlay_type": ["opportunity_zone", "qct"], "geometry": [oz, qct]},
        geometry="geometry",
        crs="EPSG:4326",
    )


def _whole_layer_county_score(parcels, scores) -> pd.DataFrame:
    ctx = ComposeContext(state_fips="05", state_name="AR", state_abbr="AR")
    ctx.set("parcel", parcels.copy())
    ctx.set("county_score", scores)
    CountyScoreLookupJoin("parcel").apply(ctx)
    return ctx.get("parcel")


def _chunked(parcels, fn) -> pd.DataFrame:
    """Annotate the parcels in two independent chunks, then concatenate —
    exactly how the streaming Composer feeds shards."""
    a = fn(parcels.iloc[:2].copy())
    b = fn(parcels.iloc[2:].copy())
    return pd.concat([a, b], ignore_index=True)


def _by_id(df: pd.DataFrame, cols: list[str]) -> dict:
    s = df.sort_values("parcel_id_full")
    return {c: list(s[c]) for c in cols}


def test_county_score_whole_layer_matches_per_chunk():
    parcels, scores = _parcels(), _scores()
    whole = _whole_layer_county_score(parcels, scores)
    chunked = _chunked(parcels, lambda c: apply_county_score(c, scores))
    cols = ["distress_tier", "persistent_poverty"]
    assert _by_id(whole, cols) == _by_id(chunked, cols)
    # And the values are actually populated (not a degenerate all-equal pass).
    assert _by_id(whole, cols)["distress_tier"] == ["distressed", "at-risk", "", "distressed"]


def test_distress_whole_layer_matches_per_chunk():
    parcels, overlays = _parcels(), _overlays()
    ctx = ComposeContext(state_fips="05", state_name="AR", state_abbr="AR")
    ctx.set("parcel", parcels.copy())
    ctx.set("distress_overlay", overlays)
    SpatialAttributeJoin(PARCEL_TO_DISTRESS_SPEC, "ParcelToDistressJoin").apply(ctx)
    whole = ctx.get("parcel")
    chunked = _chunked(parcels, lambda c: apply_parcel_to_distress(c, overlays))
    cols = ["distress_overlays", "in_oz", "in_qct"]
    assert _by_id(whole, cols) == _by_id(chunked, cols)
    assert _by_id(whole, cols)["in_oz"] == [True, True, False, True]
    assert _by_id(whole, cols)["in_qct"] == [False, True, False, False]
