"""Owners holding multiple parcels — portfolio outreach."""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import pandas as pd

from ..base import ChunkAggregator, View, register_view


@register_view
class OwnerClustersView(View):
    name = "owner_clusters"
    inputs = ["parcel"]
    description = "Owners holding ≥2 parcels in this state — portfolio outreach segment."
    write_geojson = False  # tabular only — no geometry

    def make_aggregator(self) -> ChunkAggregator:
        return OwnerClustersAggregator()


class OwnerClustersAggregator:
    """Streaming per-chunk groupby over owner clusters; re-aggregates the
    partials at finalize (sums add, firsts pick one value, anys OR)."""

    name = "owner_clusters"

    def __init__(self) -> None:
        self._partials: list[pd.DataFrame] = []

    def consume(self, chunk: gpd.GeoDataFrame) -> None:
        if "owner_cluster_id" not in chunk.columns:
            return
        df = chunk[chunk["owner_cluster_id"] != ""].copy()
        if df.empty:
            return
        # Outreach segment — drop government / school owners. They are not
        # lease-renegotiation targets and otherwise dominate the top
        # clusters (federal land holdings run into the thousands of parcels).
        if "owner_kind" in df.columns:
            df = df[~df["owner_kind"].isin(("gov", "school"))]
        if df.empty:
            return
        partial = (
            df.groupby("owner_cluster_id")
            .agg(
                parcel_count=("owner_cluster_id", "size"),
                owner_name=("owner_name", "first"),
                owner_kind=("owner_kind", "first"),
                mailing_addr=("mailing_addr", "first"),
                total_value=("assessed_value", "sum"),
                total_acres=("acreage", "sum"),
                any_infra=("has_tower", "any"),
                state_fips=("state_fips", "first"),
            )
            .reset_index()
        )
        self._partials.append(partial)

    def finalize(self, _ctx: Any) -> pd.DataFrame | None:
        if not self._partials:
            return None
        combined = pd.concat(self._partials, ignore_index=True)
        result = (
            combined.groupby("owner_cluster_id")
            .agg(
                parcel_count=("parcel_count", "sum"),
                owner_name=("owner_name", "first"),
                owner_kind=("owner_kind", "first"),
                mailing_addr=("mailing_addr", "first"),
                total_value=("total_value", "sum"),
                total_acres=("total_acres", "sum"),
                any_infra=("any_infra", "any"),
                state_fips=("state_fips", "first"),
            )
            .reset_index()
        )
        return result[result["parcel_count"] >= 2].sort_values("total_value", ascending=False)
