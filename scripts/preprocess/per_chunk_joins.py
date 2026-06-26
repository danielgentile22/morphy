"""Per-chunk feed adapters for the streaming Composer.

Thin wrappers that feed each parcel shard to the shared annotators in
:mod:`preprocess.annotators`. The annotators hold the one deep
implementation per concept; these adapters exist only to fit the
streaming chunk loop's call shape (and, for owner-cluster, to thread the
pre-pass aggregate through).

The whole-layer feed for the parametric concepts (county_score / distress
on tower / solar targets) lives in the registered Joins — which call the
*same* annotators — so each annotation is computed in exactly one place,
with no twin to drift against.

Kept separate from :mod:`preprocess.compose` so the orchestrator stays
focused on sequencing (load → pre-passes → chunk loop → write).
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from .annotators import county_score, interestingness, owner_cluster, parcel_hosts_infra
from .annotators import spatial_attribute as sa
from .joins.spatial_attribute import PARCEL_TO_DISTRESS_SPEC


def attach_owner_cluster(chunk: gpd.GeoDataFrame, lookup: pd.DataFrame) -> gpd.GeoDataFrame:
    """Annotate a parcel chunk with owner_cluster_* columns.

    ``lookup`` is the whole-state aggregate from
    ``owner_cluster.prepare`` (built once in the Composer pre-pass).
    """
    return owner_cluster.annotate(chunk, lookup)


def apply_parcel_hosts_infra(
    chunk: gpd.GeoDataFrame,
    tower_counts: dict[str, int],
    solar_counts: dict[str, int],
    tower_summary: dict[str, list[dict]],
    solar_summary: dict[str, list[dict]],
) -> gpd.GeoDataFrame:
    """Feed a parcel chunk + infra reverse-maps to the hosts-infra annotator."""
    return parcel_hosts_infra.annotate(
        chunk,
        tower_counts=tower_counts,
        solar_counts=solar_counts,
        tower_summary=tower_summary,
        solar_summary=solar_summary,
    )


def apply_county_score(chunk: gpd.GeoDataFrame, prepared: pd.DataFrame | None) -> gpd.GeoDataFrame:
    """Copy distress columns onto a parcel chunk from an already-prepared
    county_score rollup.

    The ``prepare`` rollup is chunk-independent, so the Composer hoists it
    *once* before the shard loop and passes the result here (PERF-021) — was
    re-rolled per shard (~67× for FL). Pass ``county_score.prepare(scores)``.
    """
    return county_score.annotate(chunk, prepared)


def apply_parcel_to_distress(
    chunk: gpd.GeoDataFrame, overlays: gpd.GeoDataFrame | None
) -> gpd.GeoDataFrame:
    """Annotate a parcel chunk with distress-overlay membership.

    Parcels filter invalid/null geometry out of the sjoin — their
    polygons can be invalid; the tower feed (point geometry) does not.
    """
    return sa.annotate(chunk, overlays, PARCEL_TO_DISTRESS_SPEC, filter_invalid_target_geom=True)


def apply_interestingness_score(chunk: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Feed a parcel chunk to the interestingness annotator."""
    return interestingness.annotate(chunk)
