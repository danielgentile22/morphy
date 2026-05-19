"""Owner clustering: group parcels by normalized owner+address.

Annotates each parcel with owner_cluster_id, owner_cluster_size,
owner_cluster_value_total. Cluster id is a sha1 hash of the
(normalized_owner, normalized_addr) pair — stable across runs.
"""

from __future__ import annotations

import pandas as pd

from ..base import ComposeContext, Join, register_join
from ..cluster import cluster_id


@register_join
class OwnerClusterJoin(Join):
    name = "OwnerClusterJoin"
    inputs = ["parcel"]
    annotates = "parcel"
    columns_added = [
        "owner_cluster_id",
        "owner_cluster_size",
        "owner_cluster_value_total",
    ]

    def apply(self, ctx: ComposeContext) -> None:
        parcels = ctx.get("parcel")
        if parcels is None:
            return
        parcels = parcels.copy()
        parcels["owner_cluster_id"] = [
            cluster_id(o, a)
            for o, a in zip(
                parcels.get("owner_name_norm", ""), parcels.get("mailing_addr_norm", "")
            )
        ]
        # Compute cluster size + total value via groupby.
        non_empty = parcels[parcels["owner_cluster_id"] != ""]
        if len(non_empty) > 0:
            agg = (
                non_empty.groupby("owner_cluster_id")
                .agg(
                    owner_cluster_size=("owner_cluster_id", "size"),
                    owner_cluster_value_total=("assessed_value", "sum"),
                )
                .reset_index()
            )
        else:
            agg = pd.DataFrame(
                columns=["owner_cluster_id", "owner_cluster_size", "owner_cluster_value_total"]
            )
        merged = parcels.merge(agg, on="owner_cluster_id", how="left", suffixes=("", "_new"))
        # Overwrite the initial 0 with the real cluster size.
        if "owner_cluster_size_new" in merged.columns:
            merged["owner_cluster_size"] = merged["owner_cluster_size_new"].fillna(1).astype(int)
            merged["owner_cluster_value_total"] = (
                merged["owner_cluster_value_total_new"].fillna(0).astype(float)
            )
            merged = merged.drop(
                columns=["owner_cluster_size_new", "owner_cluster_value_total_new"]
            )
        else:
            merged["owner_cluster_size"] = merged["owner_cluster_size"].fillna(1).astype(int)
            merged["owner_cluster_value_total"] = (
                merged["owner_cluster_value_total"].fillna(0).astype(float)
            )
        # Restore GeoDataFrame typing.
        import geopandas as gpd

        merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=parcels.crs)
        ctx.set("parcel", merged)
        ctx.join_log.append(self.name)
