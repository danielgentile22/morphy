"""Attribute join: county_score → tower by county_fips."""

from __future__ import annotations

import geopandas as gpd

from ..base import ComposeContext, Join, register_join


@register_join
class CountyScoreToTowerJoin(Join):
    name = "CountyScoreToTowerJoin"
    inputs = ["tower", "county_score"]
    annotates = "tower"
    columns_added = ["distress_tier", "persistent_poverty"]

    def apply(self, ctx: ComposeContext) -> None:
        towers = ctx.get("tower")
        scores = ctx.get("county_score")
        if towers is None or scores is None or len(scores) == 0:
            return
        agg = scores.groupby("county_fips").agg({
            "tier": lambda x: next((v for v in x if v), ""),
            "persistent_poverty": "any",
        }).reset_index()
        # Drop placeholders if a tower source ever populates them (defensive,
        # parallels CountyScoreToParcelJoin which hit a real KeyError here).
        towers = towers.drop(columns=[c for c in ("distress_tier", "persistent_poverty") if c in towers.columns])
        merged = towers.merge(
            agg.rename(columns={"tier": "distress_tier"}),
            on="county_fips", how="left",
        )
        if "geometry" in merged.columns:
            merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=towers.crs)
        merged["distress_tier"] = merged["distress_tier"].fillna("")
        merged["persistent_poverty"] = merged["persistent_poverty"].fillna(False)
        ctx.set("tower", merged)
        ctx.join_log.append(self.name)
