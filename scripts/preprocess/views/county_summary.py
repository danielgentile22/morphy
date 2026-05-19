"""Per-county rollup — what's in each county of this state."""

from __future__ import annotations

from ..base import ComposeContext, View, register_view


@register_view
class CountySummaryView(View):
    name = "county_summary"
    inputs = ["parcel"]
    description = (
        "Per-county rollup: parcel count, total assessed value, infra "
        "counts (tower/solar/billboard), distress flags, top owners. "
        "Foundation for county-level dashboards."
    )
    write_geojson = False

    def build(self, ctx: ComposeContext):
        parcels = ctx.get("parcel")
        if parcels is None:
            return None
        df = parcels.copy()
        agg = (
            df.groupby("county_fips")
            .agg(
                parcel_count=("parcel_id_full", "size"),
                total_assessed_value=("assessed_value", "sum"),
                total_acres=("acreage", "sum"),
                tower_count=("tower_count", "sum"),
                solar_count=("solar_count", "sum"),
                billboard_count=("billboard_count", "sum"),
                parcels_hosting_infra=("has_tower", "sum"),  # approx; refined below
                parcels_in_oz=("in_oz", "sum"),
                parcels_in_qct=("in_qct", "sum"),
                distress_tier=("distress_tier", "first"),
                persistent_poverty=("persistent_poverty", "any"),
                llc_owner_count=("owner_kind", lambda x: (x == "llc").sum()),
            )
            .reset_index()
        )
        # Refine parcels_hosting_infra to count parcels with ANY infra type.
        df["_any_infra"] = df["has_tower"] | df["has_solar"] | df["has_billboard"]
        infra = (
            df.groupby("county_fips")["_any_infra"]
            .sum()
            .reset_index(name="parcels_hosting_infra_total")
        )
        agg = agg.merge(infra, on="county_fips", how="left")
        agg["parcels_hosting_infra"] = agg["parcels_hosting_infra_total"]
        agg = agg.drop(columns=["parcels_hosting_infra_total"])
        return agg.sort_values("parcels_hosting_infra", ascending=False)
