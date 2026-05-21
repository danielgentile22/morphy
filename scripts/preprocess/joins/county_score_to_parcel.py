"""Attribute join: county_score → parcel by county_fips."""

from __future__ import annotations

from ..base import ComposeContext, Join, register_join, safe_merge


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
        agg = (
            scores.groupby("county_fips")
            .agg(
                {
                    "tier": lambda x: next((v for v in x if v), ""),
                    "persistent_poverty": "any",
                }
            )
            .reset_index()
            .rename(columns={"tier": "distress_tier"})
        )
        merged = safe_merge(
            parcels, agg, on="county_fips", columns_added=self.columns_added
        )
        merged["distress_tier"] = merged["distress_tier"].fillna("")
        merged["persistent_poverty"] = merged["persistent_poverty"].fillna(False)
        ctx.set("parcel", merged)
        ctx.join_log.append(self.name)
