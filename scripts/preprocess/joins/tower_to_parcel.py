"""Spatial join: tower (point) → parcel (polygon).

Annotates each tower row with `parcel_id_full`, `parcel_owner`,
`parcel_value`, `parcel_acreage`, `parcel_use_code` columns from the
parcel that contains it. Towers outside any parcel get nulls.
"""

from __future__ import annotations

import geopandas as gpd

from ..base import ComposeContext, Join, register_join


@register_join
class TowerToParcelJoin(Join):
    name = "TowerToParcelJoin"
    inputs = ["tower", "parcel"]
    annotates = "tower"
    columns_added = [
        "parcel_id_full", "parcel_owner", "parcel_value",
        "parcel_acreage", "parcel_use_code",
    ]

    def apply(self, ctx: ComposeContext) -> None:
        towers = ctx.get("tower")
        parcels = ctx.get("parcel")
        if towers is None or parcels is None:
            return
        # Project parcel columns to be joined.
        keep = ["parcel_id_full", "owner_name", "assessed_value",
                "acreage", "land_use_code", "geometry"]
        keep = [c for c in keep if c in parcels.columns]
        right = parcels[keep].rename(columns={
            "owner_name": "parcel_owner",
            "assessed_value": "parcel_value",
            "acreage": "parcel_acreage",
            "land_use_code": "parcel_use_code",
        })
        joined = gpd.sjoin(towers, right, how="left", predicate="within")
        # Drop sjoin's index column.
        joined = joined.drop(
            columns=[c for c in joined.columns if c.startswith("index_right")]
        )
        ctx.set("tower", joined)
        ctx.join_log.append(self.name)
