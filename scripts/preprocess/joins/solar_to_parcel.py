"""Spatial join: solar facility (point/polygon) → parcel."""

from __future__ import annotations

import geopandas as gpd

from ..base import ComposeContext, Join, register_join


@register_join
class SolarToParcelJoin(Join):
    name = "SolarToParcelJoin"
    inputs = ["solar_facility", "parcel"]
    annotates = "solar_facility"
    columns_added = ["parcel_id_full", "parcel_owner"]

    def apply(self, ctx: ComposeContext) -> None:
        solar = ctx.get("solar_facility")
        parcels = ctx.get("parcel")
        if solar is None or parcels is None:
            return
        keep = [c for c in ("parcel_id_full", "owner_name", "geometry") if c in parcels.columns]
        right = parcels[keep].rename(columns={"owner_name": "parcel_owner"})
        # For polygon-geometry solar facilities, use intersects; for points, use within.
        # geopandas.sjoin works for both with intersects.
        joined = gpd.sjoin(solar, right, how="left", predicate="intersects")
        joined = joined.drop(columns=[c for c in joined.columns if c.startswith("index_right")])
        ctx.set("solar_facility", joined)
        ctx.join_log.append(self.name)
