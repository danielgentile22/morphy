"""Owner clustering: group parcels by normalized owner+address.

Annotates each parcel with owner_cluster_id, owner_cluster_size,
owner_cluster_value_total. Cluster id is a sha1 hash of the
(normalized_owner, normalized_addr) pair — stable across runs.
"""

from __future__ import annotations

import pandas as pd

from ..base import ComposeContext, Join, register_join, safe_merge
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
        # safe_merge drops the placeholder owner_cluster_size / _value_total
        # that the normalizer initialised on `parcels` before merging the real
        # aggregates in, avoiding pandas' _x/_y suffix trap, and restores
        # GeoDataFrame typing (ADR-020). owner_cluster_id is the join key (set
        # just above), not a placeholder, so it stays out of columns_added.
        merged = safe_merge(
            parcels,
            agg,
            on="owner_cluster_id",
            columns_added=["owner_cluster_size", "owner_cluster_value_total"],
        )
        # A parcel with no cluster match (incl. empty owner id) is a cluster of one.
        merged["owner_cluster_size"] = merged["owner_cluster_size"].fillna(1).astype(int)
        merged["owner_cluster_value_total"] = (
            merged["owner_cluster_value_total"].fillna(0).astype(float)
        )
        ctx.set("parcel", merged)
        ctx.join_log.append(self.name)
