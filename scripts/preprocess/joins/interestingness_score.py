"""Compute interestingness_score per parcel.

Sits at the seam between the weight-free `ScoreComponents` extractor
(`score_components`) and the weight applier (`score_weights`). Bakes the
default-profile score into parquet; also persists the raw components so
the map app can re-score live under a different profile (ADR-058).
"""

from __future__ import annotations

from ..base import ComposeContext, Join, register_join
from ..score_components import compute_components
from ..score_weights import DEFAULT_PROFILE, apply_weights


@register_join
class InterestingnessScoreJoin(Join):
    name = "InterestingnessScoreJoin"
    inputs = ["parcel"]
    annotates = "parcel"
    columns_added = [
        "interestingness_score",
        "interestingness_components",
        "interestingness_components_raw",
    ]
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
        components = parcels.apply(compute_components, axis=1)
        scored = components.apply(lambda c: apply_weights(c, DEFAULT_PROFILE))
        parcels = parcels.copy()
        parcels["interestingness_score"] = scored.apply(lambda t: t[0])
        # Post-weight breakdown — the legacy column the detail panel reads.
        parcels["interestingness_components"] = scored.apply(lambda t: t[1])
        # Weight-free raw signals — the TS scorer (ADR-058) will read this.
        parcels["interestingness_components_raw"] = components.apply(
            lambda c: c.to_dict()
        )
        ctx.set("parcel", parcels)
        ctx.join_log.append(self.name)
