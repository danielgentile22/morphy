"""Distressed parcels hosting infra — high-impact + high-priority outreach."""

from __future__ import annotations

from ..base import ChunkAggregator, View, register_view
from ..compose_helpers import FilterChunkAggregator


@register_view
class DistressedParcelsHostingInfraView(View):
    name = "distressed_parcels_hosting_infra"
    inputs = ["parcel"]
    description = (
        "Parcels in OZ, QCT, persistent-poverty county, or ARC-distressed "
        "county that also host infrastructure. The outreach segment with "
        "the largest landowner-side dollar impact per contact."
    )
    write_geojson = True

    def make_aggregator(self) -> ChunkAggregator:
        return FilterChunkAggregator(
            self.name,
            lambda df: (
                (
                    df.get("in_oz", False).fillna(False)
                    | df.get("in_qct", False).fillna(False)
                    | df.get("persistent_poverty", False).fillna(False)
                    | df.get("distress_tier", "").fillna("").isin(["distressed", "at-risk"])
                )
                & (
                    df.get("has_tower", False).fillna(False)
                    | df.get("has_solar", False).fillna(False)
                )
            ),
        )
