"""Spatial join: parcel ↔ distress overlay (OZ / QCT / etc.).

Sets in_oz, in_qct, distress_overlays (list) on each parcel.
"""

from __future__ import annotations

import geopandas as gpd

from ..base import ComposeContext, Join, register_join


@register_join
class ParcelToDistressJoin(Join):
    name = "ParcelToDistressJoin"
    inputs = ["parcel", "distress_overlay"]
    annotates = "parcel"
    columns_added = ["in_oz", "in_qct", "distress_overlays"]

    def apply(self, ctx: ComposeContext) -> None:
        parcels = ctx.get("parcel")
        overlays = ctx.get("distress_overlay")
        if parcels is None or overlays is None or len(overlays) == 0:
            return
        # For each overlay_type, flag parcels intersecting any overlay of that type.
        types_seen: set[str] = set()
        # We carry per-parcel sets of overlay_types matched.
        overlays_by_parcel: dict[int, set[str]] = {}
        for ot in overlays["overlay_type"].dropna().unique():
            subset = overlays[overlays["overlay_type"] == ot]
            try:
                hit = gpd.sjoin(
                    parcels[["geometry"]].reset_index(),
                    subset[["geometry"]],
                    how="inner",
                    predicate="intersects",
                )
            except Exception:
                continue
            for idx in hit["index"].unique():
                overlays_by_parcel.setdefault(int(idx), set()).add(ot)
            types_seen.add(ot)

        parcels = parcels.copy()
        parcels["distress_overlays"] = parcels.index.map(
            lambda i: sorted(overlays_by_parcel.get(int(i), set()))
        )
        parcels["in_oz"] = parcels["distress_overlays"].apply(lambda lst: "opportunity_zone" in lst)
        parcels["in_qct"] = parcels["distress_overlays"].apply(lambda lst: "qct" in lst)
        ctx.set("parcel", parcels)
        ctx.join_log.append(self.name)
