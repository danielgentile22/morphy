"""Per-chunk join applicators for the streaming Composer.

Each function takes one parcel shard plus the pre-pass lookups
(owner-cluster, infra→parcel reverse maps, ancillary tables) and
returns the annotated shard. They're the chunked-mode equivalents of
the registered single-pass Joins in :mod:`preprocess.joins`.

Kept separate from :mod:`preprocess.compose` so the orchestrator stays
focused on sequencing (load → pre-passes → chunk loop → write).
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from .base import safe_merge
from .cluster import cluster_id, normalize_address, normalize_owner_name


def attach_owner_cluster(chunk: gpd.GeoDataFrame, lookup: pd.DataFrame) -> gpd.GeoDataFrame:
    """Annotate a parcel chunk with owner_cluster_* columns.

    Matches ``OwnerClusterJoin`` semantics: per-row cluster_id computed
    from the chunk's own (owner_name_norm, mailing_addr_norm);
    cluster_size + cluster_value_total looked up from the global lookup
    keyed by cluster_id (unique). Robust to duplicate parcel_id_full
    values (which exist in FL FDOR NAL across counties).
    """
    chunk = chunk.copy()
    owner_norm = (
        chunk["owner_name_norm"]
        if "owner_name_norm" in chunk.columns
        else chunk.get("owner_name", "").map(normalize_owner_name)
    )
    addr_norm = (
        chunk["mailing_addr_norm"]
        if "mailing_addr_norm" in chunk.columns
        else chunk.get("mailing_addr", "").map(normalize_address)
    )
    chunk["owner_cluster_id"] = [cluster_id(o, a) for o, a in zip(owner_norm, addr_norm)]
    # Map cluster_id → (size, value_total) via the unique-index lookup.
    size_series = (
        chunk["owner_cluster_id"].map(lookup["owner_cluster_size"])
        if (len(lookup) > 0)
        else pd.Series([pd.NA] * len(chunk), index=chunk.index)
    )
    value_series = (
        chunk["owner_cluster_id"].map(lookup["owner_cluster_value_total"])
        if (len(lookup) > 0)
        else pd.Series([pd.NA] * len(chunk), index=chunk.index)
    )
    chunk["owner_cluster_size"] = size_series.fillna(1).astype(int)
    chunk["owner_cluster_value_total"] = value_series.fillna(0).astype(float)
    return chunk


def apply_parcel_hosts_infra(
    chunk: gpd.GeoDataFrame,
    tower_counts: dict[str, int],
    solar_counts: dict[str, int],
    billboard_counts: dict[str, int],
    tower_summary: dict[str, list[dict]],
    solar_summary: dict[str, list[dict]],
    billboard_summary: dict[str, list[dict]],
) -> gpd.GeoDataFrame:
    """Per-chunk equivalent of ParcelHostsInfraJoin."""
    pids = chunk["parcel_id_full"].astype(str)
    tc = pids.map(lambda p: tower_counts.get(p, 0))
    sc = pids.map(lambda p: solar_counts.get(p, 0))
    bc = pids.map(lambda p: billboard_counts.get(p, 0))

    summaries = []
    for p in pids:
        summaries.append(
            tower_summary.get(p, []) + solar_summary.get(p, []) + billboard_summary.get(p, [])
        )

    chunk = chunk.copy()
    chunk["tower_count"] = tc.astype(int).to_numpy()
    chunk["solar_count"] = sc.astype(int).to_numpy()
    chunk["billboard_count"] = bc.astype(int).to_numpy()
    chunk["has_tower"] = chunk["tower_count"] > 0
    chunk["has_solar"] = chunk["solar_count"] > 0
    chunk["has_billboard"] = chunk["billboard_count"] > 0
    chunk["infrastructure_summary"] = summaries
    return chunk


def apply_county_score(chunk: gpd.GeoDataFrame, scores: pd.DataFrame | None) -> gpd.GeoDataFrame:
    """Per-chunk equivalent of CountyScoreToParcelJoin."""
    if scores is None or len(scores) == 0:
        return chunk
    agg = (
        scores.groupby("county_fips")
        .agg(
            {
                "tier": lambda x: next((v for v in x if v), ""),
                "persistent_poverty": "any",
            }
        )
        .reset_index()
        .rename(columns={"tier": "distress_tier"})
    )
    # The normalizer initialises distress_tier / persistent_poverty as
    # placeholders, so a raw merge collides into distress_tier_x/_y and the
    # fillna below KeyErrors. safe_merge drops the placeholders first (ADR-020),
    # mirroring CountyScoreLookupJoin, and restores GeoDataFrame typing.
    merged = safe_merge(
        chunk, agg, on="county_fips", columns_added=["distress_tier", "persistent_poverty"]
    )
    merged["distress_tier"] = merged["distress_tier"].fillna("")
    merged["persistent_poverty"] = merged["persistent_poverty"].fillna(False)
    return merged


def apply_parcel_to_distress(
    chunk: gpd.GeoDataFrame, overlays: gpd.GeoDataFrame | None
) -> gpd.GeoDataFrame:
    """Per-chunk equivalent of the distress-overlay SpatialAttribute join."""
    if overlays is None or len(overlays) == 0:
        chunk = chunk.copy()
        chunk["distress_overlays"] = [[] for _ in range(len(chunk))]
        chunk["in_oz"] = False
        chunk["in_qct"] = False
        return chunk
    overlays_by_idx: dict[int, set[str]] = {}
    # Only valid geometry can intersect an overlay. Invalid/null-geom parcels
    # stay in the chunk (geometry_valid=False) but are excluded from the sjoin
    # and fall through to in_oz/in_qct=False via the index.map below.
    geo = chunk[["geometry"]].reset_index()
    geo = geo[geo.geometry.notna() & geo.geometry.is_valid]
    for ot in overlays["overlay_type"].dropna().unique():
        sub = overlays[overlays["overlay_type"] == ot]
        try:
            hit = gpd.sjoin(geo, sub[["geometry"]], how="inner", predicate="intersects")
        except Exception:
            continue
        for idx in hit["index"].unique():
            overlays_by_idx.setdefault(int(idx), set()).add(ot)
    chunk = chunk.copy()
    chunk["distress_overlays"] = chunk.index.map(
        lambda i: sorted(overlays_by_idx.get(int(i), set()))
    )
    chunk["in_oz"] = chunk["distress_overlays"].apply(lambda lst: "opportunity_zone" in lst)
    chunk["in_qct"] = chunk["distress_overlays"].apply(lambda lst: "qct" in lst)
    return chunk


def apply_interestingness_score(chunk: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Per-chunk equivalent of InterestingnessScoreJoin."""
    from .scoring import DEFAULT_PROFILE, apply_weights, compute_components

    components = chunk.apply(compute_components, axis=1)
    scored = components.apply(lambda c: apply_weights(c, DEFAULT_PROFILE))
    chunk = chunk.copy()
    chunk["interestingness_score"] = scored.apply(lambda t: t[0])
    chunk["interestingness_components"] = scored.apply(lambda t: t[1])
    chunk["interestingness_components_raw"] = components.apply(lambda c: c.to_dict())
    return chunk
