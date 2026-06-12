"""Helpers for streaming compose: shard iteration + view aggregators.

The composer (`compose.py`) processes parcels one shard at a time so
peak memory stays bounded to a single shard rather than the whole-state
union. Views need a matching streaming interface so they don't re-load
every shard into memory at the end of the run.

This module supplies:
  - `iter_state_parcel_shards`  — yields `(label, GeoDataFrame)` per
    normalized parcel shard for one state.
  - A `ChunkAggregator` protocol + ready-made implementations that cover
    every existing View pattern. county_summary is DuckDB-backed
    (PRD #135 stage 2): its consume() is a no-op and finalize() runs one
    SQL rollup over the composite shards the chunk loop just wrote.
  - `aggregator_for_view` — picks the right aggregator (or None when the
    view can't stream and must be skipped or rebuilt from disk).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Protocol

import geopandas as gpd
import pandas as pd

from . import duck
from .base import OUTPUT_BASENAMES, View, all_normalizers

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


# ── Chunk aggregator protocol ──────────────────────────────────────────────


class ChunkAggregator(Protocol):
    """Streaming counterpart to View.build(ctx).

    `consume` sees each parcel chunk in turn (potentially many calls);
    `finalize` produces the same result a single-shot `View.build(ctx)`
    would have produced over the union of those chunks.
    """

    name: str

    def consume(self, chunk: gpd.GeoDataFrame) -> None: ...
    def finalize(self, ctx: Any) -> Any: ...


# ── Four ready-made aggregators ────────────────────────────────────────────


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


class GroupbyChunkAggregator:
    """Streaming groupby with named-aggregation semantics.

    Each chunk is grouped + aggregated locally; partials accumulate in a
    list. Finalize concats and re-aggregates with combiner functions so
    sums/sizes add, firsts pick one value, anys OR.

    Used by county_summary + owner_clusters (tabular views).
    """

    def __init__(
        self,
        name: str,
        by: str,
        agg: dict[str, tuple[str, str]],
        post_filter: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
        sort_by: str | None = None,
        ascending: bool = False,
    ):
        """
        agg: dict of output_column -> (source_column, op).
        op ∈ {"sum","size","first","any","max","min"}.
        Combiner maps the same op to a chunk-of-partials combiner.
        """
        self.name = name
        self._by = by
        self._agg = agg
        self._post = post_filter
        self._sort_by = sort_by
        self._asc = ascending
        self._partials: list[pd.DataFrame] = []

    def consume(self, chunk: gpd.GeoDataFrame) -> None:
        if self._by not in chunk.columns:
            return
        # Use named-aggregation form to map each output column to (src, op).
        kwargs: dict[str, Any] = {}
        for out_col, (src_col, op) in self._agg.items():
            if op == "size":
                kwargs[out_col] = (self._by, "size")
            elif src_col not in chunk.columns:
                continue
            else:
                kwargs[out_col] = (src_col, op)
        if not kwargs:
            return
        partial = chunk.groupby(self._by).agg(**kwargs).reset_index()
        self._partials.append(partial)

    def finalize(self, _ctx: Any) -> pd.DataFrame | None:
        if not self._partials:
            return None
        combined = pd.concat(self._partials, ignore_index=True)
        # Combiner per op. "first" picks the first non-null partial value;
        # "any" / "max" / "min" / "sum" / "size" combine as their pandas
        # group-op equivalents over the partials.
        combiner_kwargs: dict[str, tuple[str, Any]] = {}
        for out_col, (_src, op) in self._agg.items():
            if out_col not in combined.columns:
                continue
            if op in ("sum", "size"):
                combiner_kwargs[out_col] = (out_col, "sum")
            elif op == "first":
                combiner_kwargs[out_col] = (out_col, "first")
            elif op == "any":
                combiner_kwargs[out_col] = (out_col, "any")
            elif op == "max":
                combiner_kwargs[out_col] = (out_col, "max")
            elif op == "min":
                combiner_kwargs[out_col] = (out_col, "min")
            else:
                # Unknown op — fall back to first.
                combiner_kwargs[out_col] = (out_col, "first")
        result = combined.groupby(self._by).agg(**combiner_kwargs).reset_index()
        if self._post is not None:
            result = self._post(result)
        if self._sort_by is not None and self._sort_by in result.columns:
            result = result.sort_values(self._sort_by, ascending=self._asc)
        return result.reset_index(drop=True)


class StateSummaryAggregator:
    """Streaming variant of `state_summary` — a one-row DataFrame.

    Bespoke because the view mixes scalar counts, top-N owners, and
    top-N counties. Top-N aggregators are reused internally.
    """

    def __init__(self, name: str = "state_summary"):
        self.name = name
        self._parcel_count = 0
        self._any_infra = 0
        self._llc = 0
        self._oz = 0
        self._qct = 0
        self._distressed = 0
        self._persistent = 0
        self._top_owners: list[pd.DataFrame] = []
        self._top_counties: list[pd.DataFrame] = []

    def consume(self, chunk: gpd.GeoDataFrame) -> None:
        df = chunk
        self._parcel_count += len(df)
        any_infra = (
            df.get("has_tower", False).fillna(False)
            | df.get("has_solar", False).fillna(False)
            | df.get("has_billboard", False).fillna(False)
        )
        self._any_infra += int(any_infra.sum())
        if "owner_kind" in df.columns:
            self._llc += int((df["owner_kind"] == "llc").sum())
        self._oz += int(df.get("in_oz", False).fillna(False).sum())
        self._qct += int(df.get("in_qct", False).fillna(False).sum())
        if "distress_tier" in df.columns:
            self._distressed += int(df["distress_tier"].fillna("").isin(["distressed"]).sum())
        self._persistent += int(df.get("persistent_poverty", False).fillna(False).sum())
        # Per-chunk partial top-20 owner aggregates (combined at finalize).
        if "owner_cluster_id" in df.columns:
            sub = df[df["owner_cluster_id"] != ""]
            if len(sub) > 0:
                owner_partial = (
                    sub.groupby("owner_cluster_id")
                    .agg(
                        owner_name=("owner_name", "first"),
                        owner_kind=("owner_kind", "first"),
                        parcel_count=("owner_cluster_id", "size"),
                        total_value=("assessed_value", "sum"),
                    )
                    .reset_index()
                )
                self._top_owners.append(owner_partial)
        # Per-chunk partial per-county aggregates.
        if "county_fips" in df.columns:
            df = df.copy()
            df["_any_infra"] = any_infra
            county_partial = (
                df.groupby("county_fips")
                .agg(
                    parcels_hosting_infra=("_any_infra", "sum"),
                    parcel_count=("parcel_id_full", "size"),
                )
                .reset_index()
            )
            self._top_counties.append(county_partial)

    def finalize(self, ctx: Any) -> pd.DataFrame:
        # Combine partials into final top-20.
        owners_top: list[dict] = []
        if self._top_owners:
            owners = pd.concat(self._top_owners, ignore_index=True)
            owners = (
                owners.groupby("owner_cluster_id")
                .agg(
                    owner_name=("owner_name", "first"),
                    owner_kind=("owner_kind", "first"),
                    parcel_count=("parcel_count", "sum"),
                    total_value=("total_value", "sum"),
                )
                .reset_index()
                .sort_values("total_value", ascending=False)
                .head(20)
            )
            owners_top = owners.to_dict(orient="records")
        counties_top: list[dict] = []
        if self._top_counties:
            counties = pd.concat(self._top_counties, ignore_index=True)
            counties = (
                counties.groupby("county_fips")
                .agg(
                    parcels_hosting_infra=("parcels_hosting_infra", "sum"),
                    parcel_count=("parcel_count", "sum"),
                )
                .reset_index()
                .sort_values("parcels_hosting_infra", ascending=False)
                .head(20)
            )
            counties_top = counties.to_dict(orient="records")

        tower_count = len(ctx.get("tower")) if ctx.has("tower") else 0
        solar_count = len(ctx.get("solar_facility")) if ctx.has("solar_facility") else 0
        billboard_count = len(ctx.get("billboard")) if ctx.has("billboard") else 0

        return pd.DataFrame(
            [
                {
                    "state_fips": ctx.state_fips,
                    "state_name": ctx.state_name,
                    "tower_count": tower_count,
                    "parcel_count": self._parcel_count,
                    "solar_facility_count": solar_count,
                    "billboard_count": billboard_count,
                    "parcels_hosting_infra": self._any_infra,
                    "llc_owned_parcels": self._llc,
                    "parcels_in_oz": self._oz,
                    "parcels_in_qct": self._qct,
                    "parcels_distressed_county": self._distressed,
                    "parcels_persistent_poverty": self._persistent,
                    "top_owners": owners_top,
                    "top_counties": counties_top,
                }
            ]
        )


# ── Aggregator factory ─────────────────────────────────────────────────────


def aggregator_for_view(view: View) -> ChunkAggregator | None:
    """Pick a streaming aggregator for a known View, or None if the view
    can't stream and needs the in-memory fallback path."""
    name = view.name
    if name == "parcels_hosting_infra":
        return FilterChunkAggregator(
            name,
            lambda df: (
                df.get("has_tower", False).fillna(False)
                | df.get("has_solar", False).fillna(False)
                | df.get("has_billboard", False).fillna(False)
            ),
        )
    if name == "distressed_parcels_hosting_infra":
        return FilterChunkAggregator(
            name,
            lambda df: (
                (
                    df.get("in_oz", False).fillna(False)
                    | df.get("in_qct", False).fillna(False)
                    | df.get("persistent_poverty", False).fillna(False)
                    | df.get("distress_tier", "").fillna("").isin(["distressed", "at-risk"])
                )
                & (
                    df.get("has_tower", False).fillna(False)
                    | df.get("has_solar", False).fillna(False)
                    | df.get("has_billboard", False).fillna(False)
                )
            ),
        )
    if name == "llc_owned_parcels_with_infra":
        owner_kinds = {"llc", "trust", "partnership"}
        return FilterChunkAggregator(
            name,
            lambda df: (
                df["owner_kind"].isin(owner_kinds)
                & (
                    df.get("has_tower", False).fillna(False)
                    | df.get("has_solar", False).fillna(False)
                    | df.get("has_billboard", False).fillna(False)
                )
            ),
        )
    if name == "interestingness_top_1000":
        return TopNChunkAggregator(
            name,
            n=1000,
            sort_column="interestingness_score",
            eligible=lambda df: (
                ~df["owner_kind"].isin(("gov", "school"))
                if "owner_kind" in df.columns
                else pd.Series(True, index=df.index)
            ),
            min_value=0.0,
        )
    if name == "county_summary":
        return CountySummarySQLAggregator()
    if name == "owner_clusters":
        return _owner_clusters_aggregator()
    if name == "state_summary":
        return StateSummaryAggregator()
    return None  # caller falls back


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
        "billboard_count",
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
      - has_tower / has_solar / has_billboard / owner_kind are optional
        with the same defaults the pandas ``.get()`` calls supplied;
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
        for c in ("has_tower", "has_solar", "has_billboard")
    }
    any_infra = f"({flags['has_tower']} OR {flags['has_solar']} OR {flags['has_billboard']})"
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
          {_sum_sql("billboard_count", int_like=int_like("billboard_count"))} AS billboard_count,
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
        # Deferred import — picks up monkeypatched roots, like _normalized_root.
        from . import COMPOSITE_ROOT

        shard_dir = COMPOSITE_ROOT / ctx.state_fips / OUTPUT_BASENAMES.get("parcel", "parcel")
        return county_summary_rollup(sorted(shard_dir.glob("*.parquet")))


def _owner_clusters_aggregator() -> ChunkAggregator:
    """Faithful streaming reproduction of OwnerClustersView."""

    class _OwnerClusters(GroupbyChunkAggregator):
        def consume(self, chunk: gpd.GeoDataFrame) -> None:
            if "owner_cluster_id" not in chunk.columns:
                return
            df = chunk[chunk["owner_cluster_id"] != ""].copy()
            if df.empty:
                return
            if "owner_kind" in df.columns:
                df = df[~df["owner_kind"].isin(("gov", "school"))]
            if df.empty:
                return
            partial = (
                df.groupby("owner_cluster_id")
                .agg(
                    parcel_count=("owner_cluster_id", "size"),
                    owner_name=("owner_name", "first"),
                    owner_kind=("owner_kind", "first"),
                    mailing_addr=("mailing_addr", "first"),
                    total_value=("assessed_value", "sum"),
                    total_acres=("acreage", "sum"),
                    any_infra=("has_tower", "any"),
                    state_fips=("state_fips", "first"),
                )
                .reset_index()
            )
            self._partials.append(partial)

        def finalize(self, _ctx: Any) -> pd.DataFrame | None:
            if not self._partials:
                return None
            combined = pd.concat(self._partials, ignore_index=True)
            result = (
                combined.groupby("owner_cluster_id")
                .agg(
                    parcel_count=("parcel_count", "sum"),
                    owner_name=("owner_name", "first"),
                    owner_kind=("owner_kind", "first"),
                    mailing_addr=("mailing_addr", "first"),
                    total_value=("total_value", "sum"),
                    total_acres=("total_acres", "sum"),
                    any_infra=("any_infra", "any"),
                    state_fips=("state_fips", "first"),
                )
                .reset_index()
            )
            return result[result["parcel_count"] >= 2].sort_values("total_value", ascending=False)

    return _OwnerClusters(name="owner_clusters", by="owner_cluster_id", agg={})
