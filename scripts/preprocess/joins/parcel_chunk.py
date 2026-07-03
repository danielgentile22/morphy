"""The chunked parcel-stream Joins (ADR-051, driven via the registry — ADR-002).

Parcels never materialize whole (ADR-051), so these registered Joins
annotate the streamed parcel shards: the Composer calls ``prepare_chunks``
once (whole-state products of the PRD #135 DuckDB pre-passes arrive via
``ctx.artifacts``), then ``apply_chunk`` per shard — iterating the same
ordered registry every other Join runs through. Bodies are the shared
annotators in :mod:`preprocess.annotators`; each annotation is computed in
exactly one place.

These three were previously "ghost" names — manifest strings with no
adapter behind them, their sequencing hardcoded in the Composer. The
``depends_on`` chain now carries that ordering: interestingness truly reads
the columns the other four write, and the intermediate links pin the output
column order (part of the byte-identical compose contract).
"""

from __future__ import annotations

from ..annotators import interestingness, owner_cluster, parcel_hosts_infra
from ..base import ComposeContext, Join, register_join

# ctx.artifacts keys the Composer fills from its pre-passes.
HOSTS_INFRA_ARTIFACT = "parcel_hosts_infra_maps"
OWNER_LOOKUP_ARTIFACT = "owner_cluster_lookup"


class _ChunkOnlyJoin(Join):
    """Base for parcel-stream joins: chunk-driven, never whole-layer."""

    chunked = True
    annotates = "parcel"
    inputs = ["parcel"]

    def is_applicable(self, ctx: ComposeContext) -> bool:
        # The parcel layer is streamed, never present in ctx.tables.
        return True

    def apply(self, ctx: ComposeContext) -> None:
        raise RuntimeError(f"{self.name} runs chunked (ADR-051) — the Composer streams it")


@register_join
class ParcelHostsInfraJoin(_ChunkOnlyJoin):
    """Per-parcel infra rollup: tower/solar counts + flags + summary list."""

    name = "ParcelHostsInfraJoin"
    columns_added = [
        "tower_count",
        "solar_count",
        "has_tower",
        "has_solar",
        "infrastructure_summary",
    ]

    def prepare_chunks(self, ctx: ComposeContext) -> None:
        self._maps = ctx.artifacts.get(HOSTS_INFRA_ARTIFACT) or {
            "tower_counts": {},
            "solar_counts": {},
            "tower_summary": {},
            "solar_summary": {},
        }

    def apply_chunk(self, chunk):
        return parcel_hosts_infra.annotate(chunk, **self._maps)

    def release_chunks(self) -> None:
        self._maps = None


@register_join
class OwnerClusterJoin(_ChunkOnlyJoin):
    """Owner-cluster identity + whole-state size/value aggregates (ADR-024)."""

    name = "OwnerClusterJoin"
    depends_on = ["ParcelToDistressJoin"]
    columns_added = ["owner_cluster_id", "owner_cluster_size", "owner_cluster_value_total"]

    def prepare_chunks(self, ctx: ComposeContext) -> None:
        self._lookup = ctx.artifacts.get(OWNER_LOOKUP_ARTIFACT)
        if self._lookup is None:
            self._lookup = owner_cluster.prepare([])

    def apply_chunk(self, chunk):
        return owner_cluster.annotate(chunk, self._lookup)

    def release_chunks(self) -> None:
        self._lookup = None


@register_join
class InterestingnessScoreJoin(_ChunkOnlyJoin):
    """Per-parcel interestingness score — reads every column the other
    chunk joins write, hence the full dependency set."""

    name = "InterestingnessScoreJoin"
    depends_on = [
        "ParcelHostsInfraJoin",
        "CountyScoreToParcelJoin",
        "ParcelToDistressJoin",
        "OwnerClusterJoin",
    ]
    columns_added = ["interestingness_score", "interestingness_components"]

    def apply_chunk(self, chunk):
        return interestingness.annotate(chunk)
