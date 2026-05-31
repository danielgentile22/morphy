"""Unit test for the owner-cluster annotator (annotators/owner_cluster.py).

The whole-layer ``OwnerClusterJoin`` was retired (it ran only in this
test; the Composer always used the streaming path). Its behaviour is now
pinned directly on the shared annotator that both feeds use: clustering
must size correctly and leave no ``_x``/``_y``/``_new`` suffix columns
behind (the column is reassigned, not merged — ADR-020), preserving
GeoDataFrame typing.
"""

from __future__ import annotations

import geopandas as gpd
from preprocess.annotators import owner_cluster
from shapely.geometry import Point


def _parcels() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "owner_name_norm": ["acme llc", "acme llc", "jane doe"],
            "mailing_addr_norm": ["1 main st", "1 main st", "2 oak ave"],
            "assessed_value": [100.0, 200.0, 50.0],
            # Placeholders the normalizer initialises; the annotator must
            # overwrite these cleanly without a suffix collision.
            "owner_cluster_id": ["", "", ""],
            "owner_cluster_size": [0, 0, 0],
            "owner_cluster_value_total": [0.0, 0.0, 0.0],
            "geometry": [Point(0, 0), Point(1, 1), Point(2, 2)],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )


def test_owner_cluster_annotator_sizes_clusters():
    parcels = _parcels()
    lookup = owner_cluster.prepare([parcels])
    out = owner_cluster.annotate(parcels, lookup)

    # The two "acme llc @ 1 main st" parcels cluster together (size 2,
    # value 300); jane doe is a cluster of one.
    assert list(out["owner_cluster_size"]) == [2, 2, 1]
    assert list(out["owner_cluster_value_total"]) == [300.0, 300.0, 50.0]
    # No merge-suffix columns left behind.
    assert not any(c.endswith(("_new", "_x", "_y")) for c in out.columns)
    # Geometry typing is preserved.
    assert isinstance(out, gpd.GeoDataFrame)
    assert out.geometry.notna().all()


def test_prepare_is_feed_agnostic():
    """One whole frame vs the same rows split into shards → identical aggregate.

    Proves the prepare seam: the streaming feed (many shards) and a
    whole-layer feed ([parcels]) build the same cluster-keyed lookup.
    """
    parcels = _parcels()
    whole = owner_cluster.prepare([parcels])
    sharded = owner_cluster.prepare([parcels.iloc[:2], parcels.iloc[2:]])
    assert whole.equals(sharded)


def test_unclusterable_owner_defaults_to_solo():
    parcels = gpd.GeoDataFrame(
        {
            "owner_name_norm": [""],
            "mailing_addr_norm": [""],
            "assessed_value": [10.0],
            "geometry": [Point(0, 0)],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )
    out = owner_cluster.annotate(parcels, owner_cluster.prepare([parcels]))
    assert out.loc[0, "owner_cluster_id"] == ""
    assert int(out.loc[0, "owner_cluster_size"]) == 1
    assert float(out.loc[0, "owner_cluster_value_total"]) == 0.0
