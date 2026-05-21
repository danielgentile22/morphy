"""Owners holding multiple parcels — portfolio outreach."""

from __future__ import annotations

from ..base import ComposeContext, View, register_view


@register_view
class OwnerClustersView(View):
    name = "owner_clusters"
    inputs = ["parcel"]
    description = "Owners holding ≥2 parcels in this state — portfolio outreach segment."
    write_geojson = False  # tabular only — no geometry

    def build(self, ctx: ComposeContext):
        parcels = ctx.get("parcel")
        if parcels is None or "owner_cluster_id" not in parcels.columns:
            return None
        df = parcels[parcels["owner_cluster_id"] != ""].copy()
        if df.empty:
            return None
        # Outreach segment — drop government / school owners. They are not
        # lease-renegotiation targets and otherwise dominate the top
        # clusters (federal land holdings run into the thousands of parcels).
        if "owner_kind" in df.columns:
            df = df[~df["owner_kind"].isin(("gov", "school"))]
        if df.empty:
            return None
        agg = (
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
        agg = agg[agg["parcel_count"] >= 2].sort_values("total_value", ascending=False)
        return agg
