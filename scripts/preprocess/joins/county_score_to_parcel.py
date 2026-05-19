"""Attribute join: county_score → parcel by county_fips."""

from __future__ import annotations

import pandas as pd

from ..base import ComposeContext, Join, register_join


@register_join
class CountyScoreToParcelJoin(Join):
    name = "CountyScoreToParcelJoin"
    inputs = ["parcel", "county_score"]
    annotates = "parcel"
    columns_added = ["distress_tier", "persistent_poverty"]

    def apply(self, ctx: ComposeContext) -> None:
        parcels = ctx.get("parcel")
        scores = ctx.get("county_score")
        if parcels is None or scores is None or len(scores) == 0:
            return
        # Collapse multiple county_score sources (ARC + USDA) into one row per FIPS.
        agg = scores.groupby("county_fips").agg({
            "tier": lambda x: next((v for v in x if v), ""),
            "persistent_poverty": "any",
        }).reset_index()
        # Parcel schema initialises distress_tier/persistent_poverty as placeholders;
        # drop them so the merge populates fresh values without _x/_y collision.
        parcels = parcels.drop(columns=[c for c in ("distress_tier", "persistent_poverty") if c in parcels.columns])
        merged = parcels.merge(
            agg.rename(columns={"tier": "distress_tier"}),
            on="county_fips", how="left",
        )
        # geopandas merge sometimes drops the geom registration; restore.
        if "geometry" in merged.columns:
            import geopandas as gpd
            merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=parcels.crs)
        merged["distress_tier"] = merged["distress_tier"].fillna("")
        merged["persistent_poverty"] = merged["persistent_poverty"].fillna(False)
        ctx.set("parcel", merged)
        ctx.join_log.append(self.name)
