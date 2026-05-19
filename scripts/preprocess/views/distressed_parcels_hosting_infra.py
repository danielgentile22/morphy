"""Distressed parcels hosting infra — high-impact + high-priority outreach."""

from __future__ import annotations

from ..base import ComposeContext, View, register_view


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

    def build(self, ctx: ComposeContext):
        parcels = ctx.get("parcel")
        if parcels is None:
            return None
        distress_mask = (
            parcels.get("in_oz", False).fillna(False)
            | parcels.get("in_qct", False).fillna(False)
            | parcels.get("persistent_poverty", False).fillna(False)
            | (parcels.get("distress_tier", "").fillna("").isin(["distressed", "at-risk"]))
        )
        infra_mask = (
            parcels.get("has_tower", False).fillna(False)
            | parcels.get("has_solar", False).fillna(False)
            | parcels.get("has_billboard", False).fillna(False)
        )
        return parcels[distress_mask & infra_mask].copy()
