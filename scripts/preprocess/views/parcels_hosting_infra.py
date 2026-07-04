"""Parcels hosting any tower / solar facility."""

from __future__ import annotations

from ..base import ChunkAggregator, View, register_view
from ..compose_helpers import FilterChunkAggregator


@register_view
class ParcelsHostingInfraView(View):
    name = "parcels_hosting_infra"
    inputs = ["parcel"]
    description = "Parcels hosting at least one tower or solar facility."
    write_geojson = True

    def make_aggregator(self) -> ChunkAggregator:
        return FilterChunkAggregator(
            self.name,
            lambda df: (
                df.get("has_tower", False).fillna(False) | df.get("has_solar", False).fillna(False)
            ),
        )
