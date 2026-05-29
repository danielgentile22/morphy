"""Parametric Join: copy parcel columns onto an infra row via sjoin.

Replaces the three near-identical per-infra files (tower_to_parcel /
solar_to_parcel / billboard_to_parcel). One declaration per infra kind:
the sjoin predicate (`within` for points, `intersects` for polygons),
the parcel columns to copy, and the renamed names. The body is shared.

Annotates each infra row with parcel-side identity + a few parcel
attributes — used downstream by ParcelHostsInfraJoin to compute the
per-parcel infrastructure summary (its mirror image).
"""

from __future__ import annotations

from typing import Literal

import geopandas as gpd

from ..base import ComposeContext, Join, register_join_instance

Predicate = Literal["intersects", "within", "contains"]


class InfraToParcelJoin(Join):
    """For each infra row, find the parcel polygon it hits and copy a
    declared set of parcel columns onto the row (with renames).
    """

    def __init__(
        self,
        *,
        target_type: str,
        name: str,
        parcel_columns_map: dict[str, str],
        predicate: Predicate = "within",
    ) -> None:
        # Mapping is parcel-side column → infra-side rename (e.g.
        # "owner_name" → "parcel_owner"). The dict keys also serve as
        # the parcel columns to keep.
        self.target_type = target_type
        self.name = name
        self.parcel_columns_map = dict(parcel_columns_map)
        self.predicate: Predicate = predicate
        self.inputs = [target_type, "parcel"]
        self.annotates = target_type
        self.columns_added = list(parcel_columns_map.values())

    def apply(self, ctx: ComposeContext) -> None:
        infra = ctx.get(self.target_type)
        parcels = ctx.get("parcel")
        if infra is None or parcels is None:
            return
        keep = [c for c in self.parcel_columns_map if c in parcels.columns]
        if "geometry" not in parcels.columns:
            return
        right = parcels[[*keep, "geometry"]].rename(columns=self.parcel_columns_map)
        joined = gpd.sjoin(infra, right, how="left", predicate=self.predicate)
        joined = joined.drop(columns=[c for c in joined.columns if c.startswith("index_right")])
        ctx.set(self.target_type, joined)
        ctx.join_log.append(self.name)


# ── Registrations ─────────────────────────────────────────────────────────


register_join_instance(
    InfraToParcelJoin(
        target_type="tower",
        name="TowerToParcelJoin",
        parcel_columns_map={
            "parcel_id_full": "parcel_id_full",
            "owner_name": "parcel_owner",
            "assessed_value": "parcel_value",
            "acreage": "parcel_acreage",
            "land_use_code": "parcel_use_code",
        },
        predicate="within",
    )
)

# Solar facilities may be polygons (utility-scale) — use intersects so a
# field on multiple parcels reports its primary parcel hit. point-only
# datasets fall back to within semantically under intersects too.
register_join_instance(
    InfraToParcelJoin(
        target_type="solar_facility",
        name="SolarToParcelJoin",
        parcel_columns_map={
            "parcel_id_full": "parcel_id_full",
            "owner_name": "parcel_owner",
        },
        predicate="intersects",
    )
)

register_join_instance(
    InfraToParcelJoin(
        target_type="billboard",
        name="BillboardToParcelJoin",
        parcel_columns_map={
            "parcel_id_full": "parcel_id_full",
            "owner_name": "parcel_owner",
        },
        predicate="within",
    )
)
