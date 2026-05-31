"""Parcel-hosts-infrastructure annotation: the per-parcel infra rollup.

Maps the has_/count columns + the JSON-serializable
infrastructure_summary onto a parcel frame from precomputed counts +
summary dicts keyed by parcel_id_full.

Building those dicts is the cross-table step that needs a whole-layer
view: the streaming Composer's infra→parcel sjoin pre-pass produces them
once (``compose._reverse_index``), then this annotates each chunk.
Parcel-only — there is no whole-layer parcel feed (the infra tables are
the ones annotated whole-layer, by the reverse InfraToParcel joins; this
is their mirror image).
"""

from __future__ import annotations

import geopandas as gpd


def annotate(
    parcels: gpd.GeoDataFrame,
    *,
    tower_counts: dict[str, int],
    solar_counts: dict[str, int],
    billboard_counts: dict[str, int],
    tower_summary: dict[str, list[dict]],
    solar_summary: dict[str, list[dict]],
    billboard_summary: dict[str, list[dict]],
) -> gpd.GeoDataFrame:
    """Add tower/solar/billboard counts + has_ flags + infrastructure_summary.

    Each summary entry carries the infra side's identity (asr_number /
    owner_name for towers, etc.), so the detail panel can render "what's
    on this parcel". Robust to duplicate parcel_id_full across counties
    (FL FDOR NAL) — the lookup is by string id, not by index.
    """
    pids = parcels["parcel_id_full"].astype(str)
    tc = pids.map(lambda p: tower_counts.get(p, 0))
    sc = pids.map(lambda p: solar_counts.get(p, 0))
    bc = pids.map(lambda p: billboard_counts.get(p, 0))

    summaries = [
        tower_summary.get(p, []) + solar_summary.get(p, []) + billboard_summary.get(p, [])
        for p in pids
    ]

    parcels = parcels.copy()
    parcels["tower_count"] = tc.astype(int).to_numpy()
    parcels["solar_count"] = sc.astype(int).to_numpy()
    parcels["billboard_count"] = bc.astype(int).to_numpy()
    parcels["has_tower"] = parcels["tower_count"] > 0
    parcels["has_solar"] = parcels["solar_count"] > 0
    parcels["has_billboard"] = parcels["billboard_count"] > 0
    parcels["infrastructure_summary"] = summaries
    return parcels
