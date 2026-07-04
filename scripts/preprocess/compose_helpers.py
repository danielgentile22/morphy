"""Helpers for streaming compose: shard iteration + aggregator building blocks.

The composer (`compose.py`) processes parcels one shard at a time so
peak memory stays bounded to a single shard rather than the whole-state
union. Views need a matching streaming interface so they don't re-load
every shard into memory at the end of the run.

This module supplies:
  - `iter_state_parcel_shards`  — yields `(label, GeoDataFrame)` per
    normalized parcel shard for one state.
  - Generic `ChunkAggregator` implementations (filter, top-N) that
    parcel Views instantiate from `View.make_aggregator` (#266 — each
    view owns its aggregation; the protocol lives in `base`).
  - `county_summary_rollup` — the county_summary view's one-shot SQL
    rollup (PRD #135 stage 2). It lives here rather than with its view
    because the equivalence harness (tests/test_duckdb_equivalence.py)
    pins this import surface.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from . import duck
from .base import OUTPUT_BASENAMES, ChunkAggregator, all_normalizers

__all__ = [
    "ChunkAggregator",
    "FilterChunkAggregator",
    "TopNChunkAggregator",
    "county_summary_rollup",
    "iter_state_parcel_shards",
]

log = logging.getLogger("preprocess.compose")


# ── Shard iteration ────────────────────────────────────────────────────────


def _normalized_root() -> Path:
    """Resolve `preprocess.NORMALIZED_ROOT` at call time.

    Deferred import — picks up `monkeypatch.setattr(preprocess,
    "NORMALIZED_ROOT", ...)` from tests, matching the pattern
    `Normalizer.load_state_data` uses.
    """
    from . import NORMALIZED_ROOT

    return NORMALIZED_ROOT


def iter_state_parcel_shards(
    state_fips: str, *, normalized_root: Path | None = None
) -> Iterator[tuple[str, gpd.GeoDataFrame]]:
    """Yield `(shard_label, parcel_chunk)` for every parcel shard relevant to a state.

    A *shard* is one normalized parquet under
    ``normalized/<source_id>/parcels/<label>.parquet`` produced by
    `ParcelNormalizer`. Each shard is filtered to `state_fips` before
    being yielded, so a multi-state source (FCC has none, but the
    abstraction supports one) only contributes its slice.

    The label combines source_id and the shard filename so that two
    sources can both contribute parcels without collision (e.g.
    `fdor_nal:alachua`, `fl_fgdl_parcels:layer3`).

    Yields `(label, GeoDataFrame)`. A shard with zero matching rows is
    skipped silently.
    """
    root = normalized_root if normalized_root is not None else _normalized_root()
    parcel_basename = OUTPUT_BASENAMES.get("parcel", "parcel")

    parcel_sources = [n for n in all_normalizers() if "parcel" in n.canonical_types]
    for n in parcel_sources:
        src_dir = root / n.source_id / parcel_basename
        if not src_dir.is_dir():
            continue
        for shard_path in sorted(src_dir.glob("*.parquet")):
            try:
                gdf = gpd.read_parquet(shard_path)
            except Exception as e:  # noqa: BLE001 — one bad shard mustn't abort the iter
                log.warning("skipping unreadable shard %s: %s", shard_path, e)
                continue
            if "state_fips" not in gdf.columns:
                log.warning("shard %s missing contractual state_fips column; skipping", shard_path)
                continue
            slice_ = gdf[gdf["state_fips"] == state_fips]
            if len(slice_) == 0:
                continue
            label = f"{n.source_id}__{shard_path.stem}"
            # Re-wrap so the slice is a proper GeoDataFrame with CRS.
            yield label, gpd.GeoDataFrame(slice_.copy(), geometry="geometry", crs="EPSG:4326")


# ── Generic aggregator building blocks ─────────────────────────────────────


class FilterChunkAggregator:
    """Streaming equivalent of `parcels[mask].copy()` views.

    Accumulates matching rows from each chunk; concatenates at finalize.
    Used by parcels_hosting_infra / distressed_parcels_hosting_infra /
    llc_owned_parcels_with_infra.
    """

    def __init__(self, name: str, mask: Callable[[pd.DataFrame], pd.Series]):
        self.name = name
        self._mask = mask
        self._buf: list[gpd.GeoDataFrame] = []

    def consume(self, chunk: gpd.GeoDataFrame) -> None:
        try:
            keep = self._mask(chunk)
        except Exception as e:  # noqa: BLE001 — mask shouldn't break the loop
            log.warning("filter aggregator %s mask raised: %s", self.name, e)
            return
        sel = chunk[keep]
        if len(sel) > 0:
            self._buf.append(sel.copy())

    def finalize(self, _ctx: Any) -> gpd.GeoDataFrame | None:
        if not self._buf:
            return None
        out = pd.concat(self._buf, ignore_index=True)
        return gpd.GeoDataFrame(out, geometry="geometry", crs="EPSG:4326")


class TopNChunkAggregator:
    """Streaming top-N by sort_column.

    Maintains an N-row buffer; each chunk → concat with buffer → re-top-N.
    Used by interestingness_top_1000.
    """

    def __init__(
        self,
        name: str,
        n: int,
        sort_column: str,
        eligible: Callable[[pd.DataFrame], pd.Series] | None = None,
        min_value: float | None = None,
    ):
        self.name = name
        self._n = n
        self._sort_col = sort_column
        self._eligible = eligible
        self._min = min_value
        self._buf: gpd.GeoDataFrame | None = None

    def consume(self, chunk: gpd.GeoDataFrame) -> None:
        if self._sort_col not in chunk.columns:
            return
        view = chunk
        if self._eligible is not None:
            view = chunk[self._eligible(chunk)]
        if len(view) == 0:
            return
        if self._buf is None:
            combined = view
        else:
            combined = pd.concat([self._buf, view], ignore_index=True)
        topped = combined.sort_values(self._sort_col, ascending=False).head(self._n)
        self._buf = gpd.GeoDataFrame(topped, geometry="geometry", crs="EPSG:4326")

    def finalize(self, _ctx: Any) -> gpd.GeoDataFrame | None:
        if self._buf is None or len(self._buf) == 0:
            return None
        out = self._buf
        if self._min is not None and self._sort_col in out.columns:
            out = out[out[self._sort_col] > self._min]
        return out.copy() if len(out) > 0 else None


# ── county_summary: one SQL rollup over the written shards (PRD #135) ─────


# Columns the retired streaming aggregator's named-agg list required; a
# chunk missing any of them raised in consume() and contributed nothing,
# so a shard whose schema lacks one is excluded from the rollup too.
_COUNTY_SUMMARY_REQUIRED = frozenset(
    {
        "county_fips",
        "parcel_id_full",
        "assessed_value",
        "acreage",
        "tower_count",
        "solar_count",
        "in_oz",
        "in_qct",
        "distress_tier",
        "persistent_poverty",
    }
)


def _sum_sql(col: str, *, int_like: bool, boolean: bool = False) -> str:
    """Mirror pandas' named-agg sum dtype behavior: integer/bool columns sum
    to int64 (no NaN possible / True counts as 1), float columns to float64
    with NULLs skipped and an all-NULL group summing to 0."""
    expr = f'CAST(p."{col}" AS BIGINT)' if boolean else f'p."{col}"'
    target = "BIGINT" if int_like else "DOUBLE"
    return f"CAST(coalesce(sum({expr}), 0) AS {target})"


def county_summary_rollup(paths: list[Path]) -> pd.DataFrame | None:
    """The county_summary view as one GROUP BY over annotated parcel shards.

    Replaces the streaming partial-groupby aggregator (PRD #135 stage 2);
    equivalence to it is pinned by tests/test_duckdb_equivalence.py:

      - a shard missing any required column contributes nothing (the
        streaming consume() raised per chunk and the loop skipped it);
      - has_tower / has_solar / owner_kind are optional with the same
        defaults the pandas ``.get()`` calls supplied;
      - ``distress_tier`` "first" / ``persistent_poverty`` "any" are
        county-constant by construction (one county_score rollup annotates
        every chunk), read in deterministic file order;
      - rows ordered by parcels_hosting_infra desc. Within ties the legacy
        order was a pandas quicksort artifact (sort_values' default kind is
        unstable) — non-contractual; this engine pins ties to county_fips
        asc, so the file is deterministic going forward;
      - sums mirror the source dtype (int64 stays int64, floats skip NULLs).
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    eligible: list[Path] = []
    col_types: dict[str, list] = {}
    for p in paths:
        try:
            schema = pq.read_schema(p)
        except Exception as e:  # noqa: BLE001 — one bad shard mustn't abort
            log.warning("county_summary rollup: skipping unreadable shard %s: %s", p, e)
            continue
        cols = set(schema.names)
        if not _COUNTY_SUMMARY_REQUIRED <= cols:
            continue
        eligible.append(p)
        for name in schema.names:
            col_types.setdefault(name, []).append(schema.field(name).type)
    if not eligible:
        return None

    def int_like(col: str) -> bool:
        return all(pa.types.is_integer(t) or pa.types.is_boolean(t) for t in col_types[col])

    def is_bool(col: str) -> bool:
        return all(pa.types.is_boolean(t) for t in col_types[col])

    union_cols = set(col_types)
    flags = {
        c: (f'coalesce(p."{c}", FALSE)' if c in union_cols else "FALSE")
        for c in ("has_tower", "has_solar")
    }
    any_infra = f"({flags['has_tower']} OR {flags['has_solar']})"
    llc = (
        "CAST(coalesce(sum(CASE WHEN p.owner_kind = 'llc' THEN 1 ELSE 0 END), 0) AS BIGINT)"
        if "owner_kind" in union_cols
        else "CAST(0 AS BIGINT)"
    )
    paths_sql = ", ".join(duck.sql_str(str(p)) for p in eligible)
    query = f"""
        SELECT
          p.county_fips,
          CAST(count(*) AS BIGINT) AS parcel_count,
          {_sum_sql("assessed_value", int_like=int_like("assessed_value"))} AS total_assessed_value,
          {_sum_sql("acreage", int_like=int_like("acreage"))} AS total_acres,
          {_sum_sql("tower_count", int_like=int_like("tower_count"))} AS tower_count,
          {_sum_sql("solar_count", int_like=int_like("solar_count"))} AS solar_count,
          CAST(coalesce(sum(CASE WHEN {any_infra} THEN 1 ELSE 0 END), 0) AS BIGINT)
            AS parcels_hosting_infra,
          {_sum_sql("in_oz", int_like=int_like("in_oz"), boolean=is_bool("in_oz"))} AS parcels_in_oz,
          {_sum_sql("in_qct", int_like=int_like("in_qct"), boolean=is_bool("in_qct"))} AS parcels_in_qct,
          first(p.distress_tier ORDER BY p.filename, p.file_row_number)
            FILTER (WHERE p.distress_tier IS NOT NULL) AS distress_tier,
          coalesce(bool_or(p.persistent_poverty), FALSE) AS persistent_poverty,
          {llc} AS llc_owner_count
        FROM read_parquet([{paths_sql}],
                          union_by_name=true, filename=true, file_row_number=true) p
        WHERE p.county_fips IS NOT NULL
        GROUP BY p.county_fips
        ORDER BY parcels_hosting_infra DESC, p.county_fips ASC
    """
    with duck.session() as con:
        return con.execute(query).df()
