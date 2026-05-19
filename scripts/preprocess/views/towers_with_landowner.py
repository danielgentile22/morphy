"""Towers that matched to a parcel (have a landowner)."""

from __future__ import annotations

from ..base import ComposeContext, View, register_view


@register_view
class TowersWithLandownerView(View):
    name = "towers_with_landowner"
    inputs = ["tower"]
    description = "Towers that successfully matched to a parcel (have an identified landowner)."
    write_geojson = True

    def build(self, ctx: ComposeContext):
        towers = ctx.get("tower")
        if towers is None or "parcel_id_full" not in towers.columns:
            return None
        mask = towers["parcel_id_full"].notna() & (towers["parcel_id_full"] != "")
        return towers[mask].copy()
