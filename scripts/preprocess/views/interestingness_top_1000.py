"""Top 1,000 parcels by interestingness_score — default outreach list."""

from __future__ import annotations

from ..base import ComposeContext, View, register_view


@register_view
class InterestingnessTop1000View(View):
    name = "interestingness_top_1000"
    inputs = ["parcel"]
    description = (
        "Top 1,000 parcels in this state ranked by interestingness_score. "
        "Default outreach list — the map app loads this for instant overlay."
    )
    write_geojson = True

    def build(self, ctx: ComposeContext):
        parcels = ctx.get("parcel")
        if parcels is None or "interestingness_score" not in parcels.columns:
            return None
        sorted_p = parcels.sort_values("interestingness_score", ascending=False)
        top = sorted_p.head(1000).copy()
        # Only keep rows with score > 0 — no point in writing 1000 zero-score parcels
        top = top[top["interestingness_score"] > 0]
        return top
