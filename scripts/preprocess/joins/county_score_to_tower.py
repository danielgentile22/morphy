"""Attribute join: county_score → tower by county_fips."""

from __future__ import annotations

from ..base import ComposeContext, Join, register_join, safe_merge


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
            towers, agg, on="county_fips", columns_added=self.columns_added
        )
        merged["distress_tier"] = merged["distress_tier"].fillna("")
        merged["persistent_poverty"] = merged["persistent_poverty"].fillna(False)
        ctx.set("tower", merged)
        ctx.join_log.append(self.name)
