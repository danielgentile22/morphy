"""Top 1,000 parcels by interestingness_score — default outreach list."""

from __future__ import annotations

import pandas as pd

from ..base import ChunkAggregator, View, register_view
from ..compose_helpers import TopNChunkAggregator


@register_view
class InterestingnessTop1000View(View):
    name = "interestingness_top_1000"
    inputs = ["parcel"]
    description = (
        "Top 1,000 parcels in this state ranked by interestingness_score. "
        "Default outreach list — the map app loads this for instant overlay."
    )
    write_geojson = True

    def make_aggregator(self) -> ChunkAggregator:
        # Outreach list — drop government / school owners so federal land
        # hosting infrastructure can't crowd out actionable targets, and
        # drop zero-score parcels at finalize.
        return TopNChunkAggregator(
            self.name,
            n=1000,
            sort_column="interestingness_score",
            eligible=lambda df: (
                ~df["owner_kind"].isin(("gov", "school"))
                if "owner_kind" in df.columns
                else pd.Series(True, index=df.index)
            ),
            min_value=0.0,
        )
