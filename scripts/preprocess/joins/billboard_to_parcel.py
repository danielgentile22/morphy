"""Spatial join: billboard (point) → parcel."""

from __future__ import annotations

import geopandas as gpd

from ..base import ComposeContext, Join, register_join


@register_join
class BillboardToParcelJoin(Join):
    name = "BillboardToParcelJoin"
    inputs = ["billboard", "parcel"]
    annotates = "billboard"
    columns_added = ["parcel_id_full", "parcel_owner"]

    def apply(self, ctx: ComposeContext) -> None:
        bb = ctx.get("billboard")
        parcels = ctx.get("parcel")
        if bb is None or parcels is None:
            return
        keep = [c for c in ("parcel_id_full", "owner_name", "geometry") if c in parcels.columns]
        right = parcels[keep].rename(columns={"owner_name": "parcel_owner"})
        joined = gpd.sjoin(bb, right, how="left", predicate="within")
        joined = joined.drop(columns=[c for c in joined.columns if c.startswith("index_right")])
        ctx.set("billboard", joined)
        ctx.join_log.append(self.name)
