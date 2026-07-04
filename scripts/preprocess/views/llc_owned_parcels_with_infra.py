"""LLC-owned parcels that host any infra — primary outreach segment."""

from __future__ import annotations

from ..base import ChunkAggregator, View, register_view
from ..compose_helpers import FilterChunkAggregator


@register_view
class LlcOwnedParcelsWithInfraView(View):
    name = "llc_owned_parcels_with_infra"
    inputs = ["parcel"]
    description = (
        "Parcels owned by an LLC, trust, or partnership that host any "
        "tower / solar facility. Highest-value outreach segment."
    )
    write_geojson = True

    def make_aggregator(self) -> ChunkAggregator:
        owner_kinds = {"llc", "trust", "partnership"}
        return FilterChunkAggregator(
            self.name,
            lambda df: (
                df["owner_kind"].isin(owner_kinds)
                & (
                    df.get("has_tower", False).fillna(False)
                    | df.get("has_solar", False).fillna(False)
                )
            ),
        )
