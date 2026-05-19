"""Compute interestingness_score per parcel."""

from __future__ import annotations

from ..base import ComposeContext, Join, register_join
from ..score import score_parcel_row


@register_join
class InterestingnessScoreJoin(Join):
    name = "InterestingnessScoreJoin"
    inputs = ["parcel"]
    annotates = "parcel"
    columns_added = ["interestingness_score", "interestingness_components"]
    depends_on = [
        "ParcelHostsInfraJoin",
        "ParcelToDistressJoin",
        "CountyScoreToParcelJoin",
        "OwnerClusterJoin",
    ]

    def apply(self, ctx: ComposeContext) -> None:
        parcels = ctx.get("parcel")
        if parcels is None:
            return
        scores = parcels.apply(score_parcel_row, axis=1)
        parcels = parcels.copy()
        parcels["interestingness_score"] = scores.apply(lambda t: t[0])
        parcels["interestingness_components"] = scores.apply(lambda t: t[1])
        ctx.set("parcel", parcels)
        ctx.join_log.append(self.name)
