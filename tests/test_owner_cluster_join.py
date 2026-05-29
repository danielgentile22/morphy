"""Unit test for OwnerClusterJoin (joins/owner_cluster.py).

The chunked Composer uses the streaming `attach_owner_cluster` path; this
registered Join is its non-streaming equivalent (kept for the manifest +
as the canonical semantics reference). The test pins its behaviour after
the ADR-020 `safe_merge` change (P3): clustering must size correctly and
leave no `_x`/`_y`/`_new` suffix columns behind.
"""

from __future__ import annotations

import geopandas as gpd
from preprocess.base import ComposeContext
from preprocess.joins.owner_cluster import OwnerClusterJoin
from shapely.geometry import Point


def _parcels() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "owner_name_norm": ["acme llc", "acme llc", "jane doe"],
            "mailing_addr_norm": ["1 main st", "1 main st", "2 oak ave"],
            "assessed_value": [100.0, 200.0, 50.0],
            # Placeholders the normalizer initialises; safe_merge must drop
            # these before merging the real aggregates in.
            "owner_cluster_id": ["", "", ""],
            "owner_cluster_size": [0, 0, 0],
            "owner_cluster_value_total": [0.0, 0.0, 0.0],
            "geometry": [Point(0, 0), Point(1, 1), Point(2, 2)],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )


def test_owner_cluster_join_sizes_clusters_via_safe_merge():
    ctx = ComposeContext(state_fips="05", state_name="Arkansas", state_abbr="AR")
    ctx.set("parcel", _parcels())

    OwnerClusterJoin().apply(ctx)
    out = ctx.get("parcel")

    # The two "acme llc @ 1 main st" parcels cluster together (size 2,
    # value 300); jane doe is a cluster of one.
    assert list(out["owner_cluster_size"]) == [2, 2, 1]
    assert list(out["owner_cluster_value_total"]) == [300.0, 300.0, 50.0]
    # safe_merge must not leave the merge-suffix columns behind.
    assert not any(c.endswith(("_new", "_x", "_y")) for c in out.columns)
    # Geometry typing is preserved.
    assert isinstance(out, gpd.GeoDataFrame)
    assert out.geometry.notna().all()
    assert "OwnerClusterJoin" in ctx.join_log
