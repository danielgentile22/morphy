"""Per-county rollup — what's in each county of this state.

DuckDB-backed (PRD #135 stage 2): the aggregator's consume() is a no-op
and finalize() runs one SQL rollup over the composite shards the chunk
loop just wrote. The rollup query itself (``county_summary_rollup``)
lives in :mod:`preprocess.compose_helpers` — the equivalence harness
(tests/test_duckdb_equivalence.py) pins that import surface.
"""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import pandas as pd

from ..base import OUTPUT_BASENAMES, ChunkAggregator, View, register_view


@register_view
class CountySummaryView(View):
    name = "county_summary"
    inputs = ["parcel"]
    description = (
        "Per-county rollup: parcel count, total assessed value, infra "
        "counts (tower/solar), distress flags, top owners. "
        "Foundation for county-level dashboards."
    )
    write_geojson = False

    def make_aggregator(self) -> ChunkAggregator:
        return CountySummarySQLAggregator()


class CountySummarySQLAggregator:
    """county_summary under the DuckDB engine (PRD #135 stage 2).

    ``consume`` is deliberately a no-op: by finalize time the chunk loop
    has written every annotated shard to ``composite/<fips>/parcels/``,
    so the per-county rollup runs as a single out-of-core GROUP BY over
    those files instead of accumulating per-chunk partials.
    """

    name = "county_summary"

    def consume(self, chunk: gpd.GeoDataFrame) -> None:
        pass

    def finalize(self, ctx: Any) -> pd.DataFrame | None:
        # Deferred imports — pick up monkeypatched roots, like
        # compose_helpers._normalized_root.
        from .. import COMPOSITE_ROOT
        from ..compose_helpers import county_summary_rollup

        shard_dir = COMPOSITE_ROOT / ctx.state_fips / OUTPUT_BASENAMES.get("parcel", "parcel")
        return county_summary_rollup(sorted(shard_dir.glob("[!.]*.parquet")))
