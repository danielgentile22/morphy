"""Attribute join: county_score → solar_facility by county_fips."""

from __future__ import annotations

import geopandas as gpd

from ..base import ComposeContext, Join, register_join


@register_join
class CountyScoreToSolarJoin(Join):
    name = "CountyScoreToSolarJoin"
    inputs = ["solar_facility", "county_score"]
    annotates = "solar_facility"
    columns_added = ["distress_tier", "persistent_poverty"]

    def apply(self, ctx: ComposeContext) -> None:
        solar = ctx.get("solar_facility")
        scores = ctx.get("county_score")
        if solar is None or scores is None or len(scores) == 0:
            return
        agg = scores.groupby("county_fips").agg({
            "tier": lambda x: next((v for v in x if v), ""),
            "persistent_poverty": "any",
        }).reset_index()
        # Defensive drop, parallels CountyScoreToParcelJoin (see comment there).
        solar = solar.drop(columns=[c for c in ("distress_tier", "persistent_poverty") if c in solar.columns])
        merged = solar.merge(
            agg.rename(columns={"tier": "distress_tier"}),
            on="county_fips", how="left",
        )
        if "geometry" in merged.columns:
            merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=solar.crs)
        merged["distress_tier"] = merged["distress_tier"].fillna("")
        merged["persistent_poverty"] = merged["persistent_poverty"].fillna(False)
        ctx.set("solar_facility", merged)
        ctx.join_log.append(self.name)
