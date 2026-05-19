"""Reverse join: count infra per parcel.

After TowerToParcel / SolarToParcel / BillboardToParcel have run, those
join the per-parcel `parcel_id_full` onto each infra row. This Join
walks the infra tables backward and sets has_tower/tower_count/...
plus a JSON-serializable infrastructure_summary on each parcel.
"""

from __future__ import annotations

from ..base import ComposeContext, Join, register_join


@register_join
class ParcelHostsInfraJoin(Join):
    name = "ParcelHostsInfraJoin"
    inputs = ["parcel"]
    annotates = "parcel"
    columns_added = [
        "has_tower",
        "tower_count",
        "has_solar",
        "solar_count",
        "has_billboard",
        "billboard_count",
        "infrastructure_summary",
    ]
    depends_on = ["TowerToParcelJoin", "SolarToParcelJoin", "BillboardToParcelJoin"]

    def apply(self, ctx: ComposeContext) -> None:
        parcels = ctx.get("parcel")
        if parcels is None:
            return

        summaries: dict[str, list[dict]] = {}

        def _index(infra_table_name: str, kind: str, id_col: str, owner_col: str) -> dict[str, int]:
            tbl = ctx.get(infra_table_name)
            counts: dict[str, int] = {}
            if tbl is None or "parcel_id_full" not in getattr(tbl, "columns", []):
                return counts
            for _, r in tbl.iterrows():
                pid = r.get("parcel_id_full")
                if pid is None or str(pid).strip() == "":
                    continue
                pid = str(pid)
                counts[pid] = counts.get(pid, 0) + 1
                summaries.setdefault(pid, []).append(
                    {
                        "type": kind,
                        "id": str(r.get(id_col) or ""),
                        "owner": str(r.get(owner_col) or ""),
                    }
                )
            return counts

        tower_counts = _index("tower", "tower", "asr_number", "owner_name")
        solar_counts = _index("solar_facility", "solar", "facility_id", "operator")
        billboard_counts = _index("billboard", "billboard", "permit_no", "owner")

        def _lookup(pid, m):
            return int(m.get(str(pid), 0)) if pid else 0

        parcels["tower_count"] = parcels["parcel_id_full"].map(lambda p: _lookup(p, tower_counts))
        parcels["solar_count"] = parcels["parcel_id_full"].map(lambda p: _lookup(p, solar_counts))
        parcels["billboard_count"] = parcels["parcel_id_full"].map(
            lambda p: _lookup(p, billboard_counts)
        )
        parcels["has_tower"] = parcels["tower_count"] > 0
        parcels["has_solar"] = parcels["solar_count"] > 0
        parcels["has_billboard"] = parcels["billboard_count"] > 0
        parcels["infrastructure_summary"] = parcels["parcel_id_full"].map(
            lambda p: summaries.get(str(p), [])
        )

        ctx.set("parcel", parcels)
        ctx.join_log.append(self.name)
