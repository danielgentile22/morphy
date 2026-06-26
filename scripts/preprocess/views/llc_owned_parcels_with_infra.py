"""LLC-owned parcels that host any infra — primary outreach segment."""

from __future__ import annotations

from ..base import ComposeContext, View, register_view


@register_view
class LlcOwnedParcelsWithInfraView(View):
    name = "llc_owned_parcels_with_infra"
    inputs = ["parcel"]
    description = (
        "Parcels owned by an LLC, trust, or partnership that host any "
        "tower / solar facility. Highest-value outreach segment."
    )
    write_geojson = True

    def build(self, ctx: ComposeContext):
        parcels = ctx.get("parcel")
        if parcels is None:
            return None
        owner_kinds = {"llc", "trust", "partnership"}
        kind_mask = parcels["owner_kind"].isin(owner_kinds)
        infra_mask = parcels.get("has_tower", False).fillna(False) | parcels.get(
            "has_solar", False
        ).fillna(False)
        return parcels[kind_mask & infra_mask].copy()
