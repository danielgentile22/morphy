"""Per-state rollup — high-level stats for this state's composite."""

from __future__ import annotations

import pandas as pd

from ..base import ComposeContext, View, register_view


@register_view
class StateSummaryView(View):
    name = "state_summary"
    inputs = ["parcel"]
    description = "State-level rollup: total counts, top owners, top counties."
    write_geojson = False

    def build(self, ctx: ComposeContext):
        parcels = ctx.get("parcel")
        if parcels is None:
            return None

        tower_count = 0
        solar_count = 0
        billboard_count = 0
        if ctx.has("tower"):
            tower_count = len(ctx.get("tower"))
        if ctx.has("solar_facility"):
            solar_count = len(ctx.get("solar_facility"))
        if ctx.has("billboard"):
            billboard_count = len(ctx.get("billboard"))

        df = parcels.copy()
        df["_any_infra"] = (
            df["has_tower"] | df["has_solar"] | df["has_billboard"]
        )

        # Top 20 owners by total assessed value
        top_owners = (
            df[df["owner_cluster_id"] != ""]
            .groupby("owner_cluster_id")
            .agg(
                owner_name=("owner_name", "first"),
                owner_kind=("owner_kind", "first"),
                parcel_count=("owner_cluster_id", "size"),
                total_value=("assessed_value", "sum"),
            )
            .reset_index()
            .sort_values("total_value", ascending=False)
            .head(20)
        )

        # Top 20 counties by parcels-hosting-infra
        top_counties = (
            df.groupby("county_fips")
            .agg(
                parcels_hosting_infra=("_any_infra", "sum"),
                parcel_count=("parcel_id_full", "size"),
            )
            .reset_index()
            .sort_values("parcels_hosting_infra", ascending=False)
            .head(20)
        )

        summary = pd.DataFrame([{
            "state_fips": ctx.state_fips,
            "state_name": ctx.state_name,
            "tower_count": tower_count,
            "parcel_count": len(parcels),
            "solar_facility_count": solar_count,
            "billboard_count": billboard_count,
            "parcels_hosting_infra": int(df["_any_infra"].sum()),
            "llc_owned_parcels": int((df["owner_kind"] == "llc").sum()),
            "parcels_in_oz": int(df.get("in_oz", False).fillna(False).sum()),
            "parcels_in_qct": int(df.get("in_qct", False).fillna(False).sum()),
            "parcels_distressed_county": int(
                df.get("distress_tier", "").fillna("").isin(["distressed"]).sum()
            ),
            "parcels_persistent_poverty": int(
                df.get("persistent_poverty", False).fillna(False).sum()
            ),
            "top_owners": top_owners.to_dict(orient="records"),
            "top_counties": top_counties.to_dict(orient="records"),
        }])
        return summary
