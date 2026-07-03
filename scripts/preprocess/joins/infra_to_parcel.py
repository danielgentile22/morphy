"""Parametric Join: copy parcel columns onto an infra row.

Replaces the three near-identical per-infra files (tower_to_parcel /
solar_to_parcel / billboard_to_parcel). One declaration per infra kind:
the spatial predicate (`within` for points, `intersects` for polygons),
the parcel columns to copy, and the renamed names. These declarations are
the single source the Composer's DuckDB pre-pass (PRD #135) builds its
lookups from — nothing re-declares them.

`apply()` attaches the pre-pass lookup (row index → parcel columns) onto
the in-memory infra layer. The mirror image — per-parcel infrastructure
summaries — is ``ParcelHostsInfraJoin`` in :mod:`.parcel_chunk`.
"""

from __future__ import annotations

from typing import Literal

import geopandas as gpd

from ..base import ComposeContext, Join, register_join_instance

Predicate = Literal["intersects", "within", "contains"]


def apply_infra_lookup(infra: gpd.GeoDataFrame, lookup: dict[int, dict]) -> gpd.GeoDataFrame:
    """Add per-row columns from `lookup` (row index → cols dict) onto `infra`."""
    if infra is None or len(infra) == 0 or not lookup:
        return infra
    infra = infra.copy()
    # Collect every column that any lookup row provides.
    cols: set[str] = set()
    for d in lookup.values():
        cols.update(d.keys())
    for col in cols:
        # bind col per-iteration (lambda is consumed immediately by .map)
        infra[col] = infra.index.map(lambda i, col=col: lookup.get(int(i), {}).get(col))
    return infra


class InfraToParcelJoin(Join):
    """For each infra row, attach the parcel it sits in (columns + renames
    declared here; the hits come from the Composer's DuckDB pre-pass)."""

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

    def artifact_key(self) -> str:
        """Where the Composer stashes this join's pre-pass lookup."""
        return f"infra_lookup:{self.name}"

    def is_applicable(self, ctx: ComposeContext) -> bool:
        # The parcel side is streamed (ADR-051) — it never appears in
        # ctx.tables; the lookup artifact stands in for it.
        return ctx.has(self.target_type)

    def apply(self, ctx: ComposeContext) -> None:
        infra = ctx.get(self.target_type)
        if infra is None:
            return
        lookup = ctx.artifacts.get(self.artifact_key(), {})
        ctx.set(self.target_type, apply_infra_lookup(infra, lookup))
        ctx.join_log.append(self.name)


# ── Registrations ─────────────────────────────────────────────────────────

TOWER_TO_PARCEL = register_join_instance(
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
SOLAR_TO_PARCEL = register_join_instance(
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

BILLBOARD_TO_PARCEL = register_join_instance(
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

INFRA_TO_PARCEL_JOINS: tuple[InfraToParcelJoin, ...] = (
    TOWER_TO_PARCEL,
    SOLAR_TO_PARCEL,
    BILLBOARD_TO_PARCEL,
)

# Parcel column → infra-side rename, unioned across the declarations above —
# consumed by the Composer's pre-pass so the SQL attach list can never drift
# from the adapters (ADR-002).
INFRA_PARCEL_RENAME: dict[str, str] = {
    src: dst
    for j in INFRA_TO_PARCEL_JOINS
    for src, dst in j.parcel_columns_map.items()
    if src != dst
}
