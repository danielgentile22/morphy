"""Parcels hosting any tower / solar facility."""

from __future__ import annotations

from ..base import ComposeContext, View, register_view


@register_view
class ParcelsHostingInfraView(View):
    name = "parcels_hosting_infra"
    inputs = ["parcel"]
    description = "Parcels hosting at least one tower or solar facility."
    write_geojson = True

    def build(self, ctx: ComposeContext):
        parcels = ctx.get("parcel")
        if parcels is None:
            return None
        mask = parcels.get("has_tower", False).fillna(False) | parcels.get(
            "has_solar", False
        ).fillna(False)
        return parcels[mask].copy()
