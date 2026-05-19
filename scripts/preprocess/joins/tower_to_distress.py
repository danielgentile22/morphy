"""Spatial join: tower ↔ distress overlay. Sets in_oz / in_qct on towers."""

from __future__ import annotations

import geopandas as gpd

from ..base import ComposeContext, Join, register_join


@register_join
class TowerToDistressJoin(Join):
    name = "TowerToDistressJoin"
    inputs = ["tower", "distress_overlay"]
    annotates = "tower"
    columns_added = ["in_oz", "in_qct", "distress_overlays"]

    def apply(self, ctx: ComposeContext) -> None:
        towers = ctx.get("tower")
        overlays = ctx.get("distress_overlay")
        if towers is None or overlays is None or len(overlays) == 0:
            return
        overlays_by_tower: dict[int, set[str]] = {}
        for ot in overlays["overlay_type"].dropna().unique():
            subset = overlays[overlays["overlay_type"] == ot]
            try:
                hit = gpd.sjoin(
                    towers[["geometry"]].reset_index(),
                    subset[["geometry"]],
                    how="inner",
                    predicate="within",
                )
            except Exception:
                continue
            for idx in hit["index"].unique():
                overlays_by_tower.setdefault(int(idx), set()).add(ot)
        towers = towers.copy()
        towers["distress_overlays"] = towers.index.map(
            lambda i: sorted(overlays_by_tower.get(int(i), set()))
        )
        towers["in_oz"] = towers["distress_overlays"].apply(lambda lst: "opportunity_zone" in lst)
        towers["in_qct"] = towers["distress_overlays"].apply(lambda lst: "qct" in lst)
        ctx.set("tower", towers)
        ctx.join_log.append(self.name)
