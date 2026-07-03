"""Per-state streaming Composer (ADR-051).

Parcels are processed one shard at a time so peak memory stays bounded
to a single shard rather than the whole-state union. FL (~11 M parcels,
historically ~19.5 GB peak when the single-shot path existed) and
NC (~5.9 M parcels) fit on a 16 GB dev machine. Small states (AR ~2.1 M,
MT ~0.9 M) use the same path — one compose surface, one bug surface.

Sharded output: parcels are written under
``composite/<fips>/parcels/<label>.parquet`` rather than as a single
``parcels.parquet``. The catalog advertises a ``sharded: true`` flag
on the parcel layer plus a directory ``parquet_path``. Downstream
readers (facets, tiles) handle the layout.

Sequence:
  1. Load ancillary tables (towers, solar, billboard, distress_overlay,
     county_score). All small enough to stay in memory.
  2. **Owner-cluster pre-pass** — one DuckDB aggregation over the
     sharded parquet (PRD #135) computes cluster sizes + value totals
     across the whole state; rows needing the Python re-normalization
     fallback are the only ones that surface into pandas.
  3. **Infra→parcel pre-pass** — one DuckDB spatial join over the
     sharded parquet (PRD #135) finds the host parcel for every tower /
     solar / billboard row; only matched rows surface into pandas.
     Applied to the in-memory infra tables after the chunk loop.
  4. **Per-chunk loop** — for each parcel shard:
        a. Run parcel-touching joins (ParcelHostsInfra,
           CountyScoreToParcel, ParcelToDistress, OwnerCluster from
           lookup, InterestingnessScore).
        b. Feed the annotated chunk to every streaming view aggregator.
        c. Write `composite/<fips>/parcels/<label>.parquet`.
  5. Run non-parcel-touching joins on towers / solar / billboard.
  6. Finalize view aggregators; write view outputs + catalog.

Joins that don't fit the chunked pattern (e.g. arbitrary new joins
declared by a future contributor) are skipped with a warning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import COMPOSITE_ROOT, duck
from .annotators import county_score, owner_cluster
from .base import (
    OUTPUT_BASENAMES,
    SPATIAL_TYPES,
    ComposeContext,
    ComposeResult,
    all_normalizers,
    all_views,
    ordered_joins,
    utcnow_iso,
)
from .catalog_builder import build_catalog, geom_type, schema_summary
from .catalog_schema import validate_catalog
from .compose_helpers import aggregator_for_view, iter_state_parcel_shards
from .geographies import StateGeography
from .io import (
    dual_write_spatial,
    write_geojson,
    write_geoparquet,
    write_json,
    write_parquet,
)
from .joins.uls_to_asr import carrier_coverage_summary
from .per_chunk_joins import (
    apply_county_score,
    apply_interestingness_score,
    apply_parcel_hosts_infra,
    apply_parcel_to_distress,
    attach_owner_cluster,
)

log = logging.getLogger("preprocess.compose")


@dataclass
class ComposeConfig:
    state: StateGeography
    skip_views: list[str] = field(default_factory=list)
    skip_joins: list[str] = field(default_factory=list)


# ── Owner-cluster pre-pass (DuckDB aggregation, PRD #135) ─────────────────


def _blank_sql(col: str) -> str:
    return f'(p."{col}" IS NULL OR trim(p."{col}") = \'\')'


def _nonblank_sql(col: str) -> str:
    return f'(p."{col}" IS NOT NULL AND trim(p."{col}") != \'\')'


def _build_owner_cluster_lookup(state_fips: str) -> pd.DataFrame:
    """Whole-state owner_cluster_id → (size, value_total) aggregate — one
    DuckDB aggregation over the sharded parquet (PRD #135 stage 3; replaced
    the per-shard column-projection scan).

    The owner-key recipe stays in :mod:`preprocess.cluster` (its single
    home). Rows whose stored ``owner_name_norm`` / ``mailing_addr_norm``
    are usable verbatim — the overwhelming majority; normalizers compute
    them for every row — are keyed in SQL with the exact ``cluster_id``
    recipe over the stored norms (``substr(sha1(name || '|' || addr), 1,
    12)``; sha1-of-UTF-8 matches hashlib). The rare rows that need the
    re-normalization fallback (blank norm with a non-blank raw value) are
    pulled into pandas and keyed through the live ``owner_cluster.prepare``
    — the Python recipe is never re-implemented in SQL. Both partial
    aggregates then combine.

    Semantics preserved from the streaming pre-pass (equivalence pinned by
    tests/test_duckdb_equivalence.py):
      - a shard missing any owner column contributes nothing (the legacy
        column-projected read raised and the shard was skipped);
      - parcels with no clusterable owner/address (key == "") are excluded;
      - assessed_value coerces non-numeric → 0 (TRY_CAST ≡ to_numeric).

    Returns a DataFrame indexed by ``owner_cluster_id`` (always unique, so
    safe to ``.map`` against even when parcel_id_full duplicates across
    shards — FL FDOR NAL). The per-row ``owner_cluster_id`` is recomputed
    on each chunk by ``owner_cluster.annotate``; this only supplies the
    global aggregates that need a whole-state pass.
    """
    empty = owner_cluster.prepare([])
    with duck.session() as con:
        shards = duck.register_state_parcels(con, state_fips)
        owner_set = set(owner_cluster.OWNER_COLS)
        eligible = [s.seq for s in shards if owner_set <= set(s.columns)]
        if not eligible:
            return empty
        in_eligible = f"p.__shard_seq IN ({', '.join(str(q) for q in eligible)})"
        name_val = (
            f"CASE WHEN NOT {_blank_sql('owner_name_norm')} THEN p.\"owner_name_norm\" ELSE '' END"
        )
        addr_val = (
            f"CASE WHEN NOT {_blank_sql('mailing_addr_norm')} "
            f"THEN p.\"mailing_addr_norm\" ELSE '' END"
        )
        needs_python = (
            f"(({_blank_sql('owner_name_norm')} AND {_nonblank_sql('owner_name')}) "
            f"OR ({_blank_sql('mailing_addr_norm')} AND {_nonblank_sql('mailing_addr')}))"
        )
        key = (
            f"CASE WHEN {name_val} = '' AND {addr_val} = '' THEN '' "
            f"ELSE substr(sha1({name_val} || '|' || {addr_val}), 1, 12) END"
        )
        sql_agg = con.execute(
            f"""
            SELECT {key} AS owner_cluster_id,
                   CAST(count(*) AS BIGINT) AS owner_cluster_size,
                   CAST(sum(coalesce(TRY_CAST(p."assessed_value" AS DOUBLE), 0.0)) AS DOUBLE)
                     AS owner_cluster_value_total
            FROM "{duck.PARCELS_VIEW}" p
            WHERE {in_eligible} AND NOT {needs_python} AND {key} != ''
            GROUP BY 1
            """
        ).df()
        fallback_cols = ", ".join(f'p."{c}"' for c in owner_cluster.OWNER_COLS)
        fallback = con.execute(
            f'SELECT {fallback_cols} FROM "{duck.PARCELS_VIEW}" p '
            f"WHERE {in_eligible} AND {needs_python}"
        ).df()
    parts = [sql_agg]
    if len(fallback) > 0:
        parts.append(owner_cluster.prepare([fallback]).reset_index())
    combined = pd.concat(parts, ignore_index=True)
    if len(combined) == 0:
        return empty
    out = combined.groupby("owner_cluster_id").agg(
        owner_cluster_size=("owner_cluster_size", "sum"),
        owner_cluster_value_total=("owner_cluster_value_total", "sum"),
    )
    out["owner_cluster_size"] = out["owner_cluster_size"].astype(int)
    out["owner_cluster_value_total"] = out["owner_cluster_value_total"].astype(float)
    return out


# ── Tower / solar / billboard pre-pass (DuckDB spatial join, PRD #135) ────


# Parcel columns renamed onto the infra row when a match is found.
_INFRA_PARCEL_RENAME = {
    "owner_name": "parcel_owner",
    "assessed_value": "parcel_value",
    "acreage": "parcel_acreage",
    "land_use_code": "parcel_use_code",
}


def _host_eligible_sql(shards: list[duck.ParcelShard]) -> str:
    """SQL predicate selecting host-eligible parcel rows.

    Per-shard semantics preserved from the streaming pre-pass: a shard
    carrying the normalize-time ``geometry_valid`` column (PERF-028) trusts
    it (NULL → False); a shard without it falls back to GEOS validity.
    Invalid/null-geom parcels can't host infrastructure and would corrupt
    the join — they stay in the parcel output, just excluded here."""
    flag = 'coalesce(p."geometry_valid", FALSE)'
    geos = "(p.geometry IS NOT NULL AND ST_IsValid(p.geometry))"
    flagged = [s.seq for s in shards if "geometry_valid" in s.columns]
    if not flagged:
        return geos
    if len(flagged) == len(shards):
        return flag
    seqs = ", ".join(str(q) for q in flagged)
    return f"(CASE WHEN p.__shard_seq IN ({seqs}) THEN {flag} ELSE {geos} END)"


def _build_infra_to_parcel_lookups(
    specs: dict[str, tuple[gpd.GeoDataFrame | None, list[str]]],
    state_fips: str,
) -> dict[str, dict[int, dict]]:
    """For every infra layer in `specs`, find the parcel each infra row sits in
    — one DuckDB spatial join over the state's sharded parquet (PRD #135).

    `specs` maps a layer name → (infra GeoDataFrame, keep_cols). All layers
    ride one query (one parcel sweep, one R-tree — the single-pass property
    PERF-016 established), and the engine is out-of-core: parcel shards never
    load into pandas here; only the small infra geometries go in and only the
    matched rows come back.

    Semantics preserved from the streaming pre-pass this replaced
    (equivalence pinned by tests/test_duckdb_equivalence.py):
      - host-eligible parcels only (see `_host_eligible_sql`);
      - first match wins, in canonical shard order then within-shard row
        order — a tower in two overlapping parcels is rare and this stage
        never disambiguated beyond first-encountered;
      - a keep-column is attached iff the matched shard's schema has it, so
        per-shard schema variance behaves exactly as before.

    Returns {name: {infra_row_index: attach_dict}}; a None/empty layer → {}.
    """
    out: dict[str, dict[int, dict]] = {name: {} for name in specs}
    active = {
        name: (infra, keep_cols)
        for name, (infra, keep_cols) in specs.items()
        if infra is not None and len(infra) > 0
    }
    if not active:
        return out
    with duck.session() as con:
        shards = duck.register_state_parcels(con, state_fips)
        if not shards:
            return out
        union_cols = set().union(*(s.columns for s in shards))
        if "geometry" not in union_cols:
            return out
        infra_rows = pd.concat(
            [
                pd.DataFrame(
                    {
                        "layer": name,
                        "infra_idx": [int(i) for i in infra.index],
                        "wkb": infra.geometry.to_wkb(),
                    }
                )
                for name, (infra, _keep) in active.items()
            ],
            ignore_index=True,
        )
        con.register("__infra_rows", infra_rows)
        con.execute(
            "CREATE OR REPLACE TEMP TABLE __infra_geo AS "
            "SELECT layer, infra_idx, ST_GeomFromWKB(wkb) AS geom FROM __infra_rows"
        )
        keep_union = [
            c
            for c in dict.fromkeys(c for _, keep in active.values() for c in keep)
            if c in union_cols
        ]
        attach_sql = "".join(f', p."{c}" AS "{_INFRA_PARCEL_RENAME.get(c, c)}"' for c in keep_union)
        rows = con.execute(
            f"""
            WITH hits AS (
              SELECT i.layer, i.infra_idx, p.__shard_seq{attach_sql},
                     ROW_NUMBER() OVER (
                       PARTITION BY i.layer, i.infra_idx
                       ORDER BY p.__shard_seq, p.__row_idx
                     ) AS rn
              FROM __infra_geo i
              JOIN "{duck.PARCELS_VIEW}" p ON ST_Within(i.geom, p.geometry)
              WHERE {_host_eligible_sql(shards)}
            )
            SELECT * EXCLUDE (rn) FROM hits WHERE rn = 1
            ORDER BY __shard_seq, infra_idx
            """
        ).fetchall()
        shard_cols = {s.seq: frozenset(s.columns) for s in shards}
        keep_by_layer = {name: set(keep) for name, (_infra, keep) in active.items()}
        for layer, idx, seq, *values in rows:
            have = shard_cols[seq] & keep_by_layer[layer]
            out[layer][int(idx)] = {
                _INFRA_PARCEL_RENAME.get(c, c): v for c, v in zip(keep_union, values) if c in have
            }
    return out


def _apply_lookup(infra: gpd.GeoDataFrame, lookup: dict[int, dict]) -> gpd.GeoDataFrame:
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


# ── Top-level orchestrator ────────────────────────────────────────────────


def compose(cfg: ComposeConfig) -> ComposeResult:
    """Per-state streaming Composer. See module docstring."""
    state: StateGeography = cfg.state
    log.info("=== compose state %s (%s) ===", state.fips, state.name)

    ctx = ComposeContext(
        state_fips=state.fips,
        state_name=state.name,
        state_abbr=state.abbr,
    )

    out_dir = COMPOSITE_ROOT / state.fips
    out_dir.mkdir(parents=True, exist_ok=True)
    parcels_shard_dir = out_dir / OUTPUT_BASENAMES.get("parcel", "parcel")
    # Clean any pre-existing shards from a previous run so the new ones
    # don't accidentally co-exist with stale ones.
    if parcels_shard_dir.exists():
        for old in parcels_shard_dir.glob("*.parquet"):
            old.unlink()
    parcels_shard_dir.mkdir(parents=True, exist_ok=True)
    # Remove a legacy single-file parcels.parquet from a non-chunked run
    # so downstream readers don't see both layouts at once.
    legacy_single = out_dir / "parcels.parquet"
    if legacy_single.exists():
        legacy_single.unlink()
    views_dir = out_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)

    # 1. Ancillary tables -----------------------------------------------------
    sources_used = _load_state_data(ctx)
    log.info(
        "loaded %d non-parcel canonical types from %d sources",
        len(ctx.tables),
        len(sources_used),
    )

    # 2. Owner-cluster pre-pass ---------------------------------------------
    log.info("owner-cluster pre-pass (DuckDB)…")
    owner_lookup = _build_owner_cluster_lookup(state.fips)
    log.info("owner-cluster pre-pass: %d parcels indexed", len(owner_lookup))

    # 3. Infra→parcel pre-pass (one DuckDB spatial join, all layers — PRD #135)
    log.info("infra→parcel pre-pass (DuckDB)…")
    infra_lookups = _build_infra_to_parcel_lookups(
        {
            "tower": (
                ctx.get("tower"),
                [
                    "parcel_id_full",
                    "owner_name",
                    "assessed_value",
                    "acreage",
                    "land_use_code",
                ],
            ),
            "solar": (ctx.get("solar_facility"), ["parcel_id_full", "owner_name"]),
            "billboard": (ctx.get("billboard"), ["parcel_id_full", "owner_name"]),
        },
        state.fips,
    )
    tower_lookup = infra_lookups["tower"]
    solar_lookup = infra_lookups["solar"]
    billboard_lookup = infra_lookups["billboard"]
    log.info(
        "infra→parcel lookups: towers=%d, solar=%d, billboards=%d",
        len(tower_lookup),
        len(solar_lookup),
        len(billboard_lookup),
    )

    #    Build per-parcel reverse maps (parcel_id_full → infra counts +
    #    summary list) from the lookups built above. This replaces the
    #    iter-over-infra-rows logic of ParcelHostsInfraJoin without
    #    needing a single in-memory parcel table.
    tower_counts, tower_summary = _reverse_index(
        tower_lookup,
        infra=ctx.get("tower"),
        kind="tower",
        # The union-wide structure identity: the FCC registration number on
        # fcc_asr rows, the FAA obstacle number on faa_oeaaa rows. asr_number
        # is FCC-only since the M-i namespace split (#215); values here are
        # unchanged (the mixed asr_number used to carry exactly these ids).
        id_col="_source_row_id",
        owner_col="owner_name",
    )
    solar_counts, solar_summary = _reverse_index(
        solar_lookup,
        infra=ctx.get("solar_facility"),
        kind="solar",
        id_col="facility_id",
        owner_col="operator",
    )
    # Billboards are no longer rolled up onto parcels (E14): every source is
    # deferred (MACRO-9), so the per-parcel counts were 0 on 100% of rows. The
    # billboard layer itself is still composed below (billboard_lookup) so the
    # plumbing is ready when a source is acquired.

    # 4. Per-chunk loop -----------------------------------------------------
    # Hoist the county_score rollup out of the shard loop (PERF-021): it's a
    # groupby over the small, chunk-independent county_score table, so computing
    # it once and reusing it per shard is identical output, far less work.
    county_score_prepared = county_score.prepare(ctx.get("county_score"))
    view_aggregators = _build_view_aggregators()
    skipped_views: list[str] = []
    for v in all_views():
        if v.name not in {a.name for a in view_aggregators}:
            # Tower-only / non-parcel views still build at the end via
            # the in-memory ctx (towers + solar + billboard fit easily).
            if "parcel" in v.inputs:
                skipped_views.append(v.name)

    shard_count = 0
    total_parcel_rows = 0
    shard_files: list[Path] = []
    parcel_schema: dict[str, str] | None = None
    parcel_geom_type: str = ""

    for label, chunk in iter_state_parcel_shards(state.fips):
        # Parcel-touching joins, applied directly on the chunk.
        chunk = apply_parcel_hosts_infra(
            chunk,
            tower_counts,
            solar_counts,
            tower_summary,
            solar_summary,
        )
        chunk = apply_county_score(chunk, county_score_prepared)
        chunk = apply_parcel_to_distress(chunk, ctx.get("distress_overlay"))
        chunk = attach_owner_cluster(chunk, owner_lookup)
        chunk = apply_interestingness_score(chunk)

        # Feed view aggregators.
        for agg in view_aggregators:
            try:
                agg.consume(chunk)
            except Exception as e:  # noqa: BLE001
                log.warning("view aggregator %s consume raised: %s", agg.name, e)

        # Write the shard.
        shard_path = parcels_shard_dir / f"{label}.parquet"
        write_geoparquet(chunk, shard_path)
        shard_files.append(shard_path)
        shard_count += 1
        total_parcel_rows += len(chunk)
        if parcel_schema is None:
            parcel_schema = schema_summary(chunk)
            parcel_geom_type = geom_type(chunk)
        log.info("  ✓ shard %s (%d rows) → %s", label, len(chunk), shard_path.name)

    log.info("chunk loop done: %d shards, %d parcels", shard_count, total_parcel_rows)

    # 5. Apply infra→parcel lookups onto the in-memory infra tables, then
    #    run non-parcel-touching joins (CountyScoreToTower etc.) via the
    #    standard registry — they don't need parcels in ctx.
    if ctx.has("tower"):
        ctx.set("tower", _apply_lookup(ctx.get("tower"), tower_lookup))
    if ctx.has("solar_facility"):
        ctx.set("solar_facility", _apply_lookup(ctx.get("solar_facility"), solar_lookup))
    if ctx.has("billboard"):
        ctx.set("billboard", _apply_lookup(ctx.get("billboard"), billboard_lookup))

    joins_applied = [
        "ParcelHostsInfraJoin",
        "CountyScoreToParcelJoin",
        "ParcelToDistressJoin",
        "OwnerClusterJoin",
        "InterestingnessScoreJoin",
        "TowerToParcelJoin",
        "SolarToParcelJoin",
        "BillboardToParcelJoin",
    ]
    joins_skipped: list[str] = list(cfg.skip_joins or [])
    for j in ordered_joins():
        # Skip parcel-touching joins (already done streaming above).
        if j.annotates == "parcel" or j.name in joins_applied:
            continue
        if j.name in joins_skipped:
            continue
        if not j.is_applicable(ctx):
            joins_skipped.append(j.name)
            continue
        try:
            j.apply(ctx)
            joins_applied.append(j.name)
            log.info("✓ post-chunk join %s", j.name)
        except Exception as e:  # noqa: BLE001
            log.error("✗ post-chunk join %s failed: %s", j.name, e)
            ctx.warnings.append(f"join {j.name} failed: {e}")

    # 6. Write non-parcel canonical-type outputs (towers, solar, billboard,
    #    distress_overlay, county_score, etc.) using the same logic as
    #    `compose.compose()`.
    output_files: list[Path] = []
    counts: dict[str, int] = {"parcel": total_parcel_rows}
    output_files.extend(shard_files)

    for ct, table in ctx.tables.items():
        if ct == "parcel":
            continue
        if table is None or len(table) == 0:
            continue
        basename = OUTPUT_BASENAMES.get(ct, ct)
        if ct in SPATIAL_TYPES:
            files, _ = dual_write_spatial(table, out_dir, basename)
            output_files.extend(files)
        else:
            p = out_dir / f"{basename}.parquet"
            write_parquet(table, p)
            output_files.append(p)
        counts[ct] = len(table)

    # 7. Finalize streaming views + run non-streaming views in-memory.
    views_built: list[str] = []
    view_meta: dict[str, dict] = {}
    aggregators_by_name = {a.name: a for a in view_aggregators}
    for v in all_views():
        if v.name in (cfg.skip_views or []):
            continue
        agg = aggregators_by_name.get(v.name)
        result = None
        try:
            if agg is not None:
                result = agg.finalize(ctx)
            elif "parcel" not in v.inputs:
                if not v.is_applicable(ctx):
                    continue
                result = v.build(ctx)
            else:
                ctx.warnings.append(
                    f"view {v.name} has no streaming aggregator — skipped under chunked mode"
                )
                continue
        except Exception as e:  # noqa: BLE001
            log.error("✗ view %s failed: %s", v.name, e)
            ctx.warnings.append(f"view {v.name} failed: {e}")
            continue
        if result is None or len(result) == 0:
            continue
        views_built.append(v.name)
        p_parquet = views_dir / f"{v.name}.parquet"
        if isinstance(result, gpd.GeoDataFrame) and getattr(result, "geometry", None) is not None:
            write_geoparquet(result, p_parquet)
            output_files.append(p_parquet)
            view_meta[v.name] = {
                "rows": len(result),
                "geometry_type": geom_type(result),
                "parquet_path": f"views/{v.name}.parquet",
                "description": v.description,
                "inputs": v.inputs,
            }
            if v.write_geojson:
                p_geo = views_dir / f"{v.name}.geojson"
                write_geojson(result, p_geo)
                output_files.append(p_geo)
                view_meta[v.name]["geojson_path"] = f"views/{v.name}.geojson"
        else:
            write_parquet(
                result if isinstance(result, pd.DataFrame) else pd.DataFrame(result),
                p_parquet,
            )
            output_files.append(p_parquet)
            view_meta[v.name] = {
                "rows": len(result),
                "geometry_type": None,
                "parquet_path": f"views/{v.name}.parquet",
                "description": v.description,
                "inputs": v.inputs,
            }
        log.info("✓ view %s (%d rows)", v.name, len(result))

    # 8. Catalog + summary (sharded layer descriptor for parcels).
    catalog = build_catalog(
        state,
        ctx,
        view_meta,
        out_dir,
        sources_used,
        sharded_parcels={
            "shard_count": shard_count,
            "shard_dir": OUTPUT_BASENAMES.get("parcel", "parcel"),
            "rows": total_parcel_rows,
            "schema": parcel_schema or {},
            "geometry_type": parcel_geom_type,
        },
    )
    validate_catalog(catalog)
    catalog_path = out_dir / "catalog.json"
    write_json(catalog, catalog_path)
    output_files.append(catalog_path)

    # Slice A (#24): carrier-identification coverage — share of FCC ASR towers
    # carrying ≥ 1 ULS carrier. ctx still holds the in-memory tower table with
    # `carriers` as Python lists (write_geoparquet JSON-encodes a copy, not ctx).
    carrier_coverage = carrier_coverage_summary(ctx.get("tower"))
    if carrier_coverage.get("computed"):
        log.info(
            "carrier coverage %s: %.1f%% of FCC ASR towers (%d/%d) — verified=%d likely=%d possible=%d",
            state.fips,
            carrier_coverage["coverage_pct"],
            carrier_coverage["asr_towers_with_carrier"],
            carrier_coverage["asr_towers"],
            carrier_coverage["by_confidence"]["verified"],
            carrier_coverage["by_confidence"]["likely"],
            carrier_coverage["by_confidence"]["possible"],
        )

    summary = {
        "state_fips": state.fips,
        "state_name": state.name,
        "state_abbr": state.abbr,
        "generated_at": utcnow_iso(),
        "sources_used": sources_used,
        "joins_applied": joins_applied,
        "joins_skipped": joins_skipped,
        "views_built": views_built,
        "counts": counts,
        "carrier_coverage": carrier_coverage,
        "warnings": ctx.warnings,
        "chunked": True,
        "parcel_shards": shard_count,
    }
    summary_path = out_dir / "summary.json"
    write_json(summary, summary_path)
    output_files.append(summary_path)

    log.info(
        "compose %s complete: %d sources, %d shards, %d joins, %d views",
        state.fips,
        len(sources_used),
        shard_count,
        len(joins_applied),
        len(views_built),
    )

    return ComposeResult(
        state_fips=state.fips,
        sources_used=sources_used,
        joins_applied=joins_applied,
        joins_skipped=joins_skipped,
        views_built=views_built,
        counts=counts,
        output_files=output_files,
    )


# ── Helpers ────────────────────────────────────────────────────────────────


def _reverse_index(
    lookup: dict[int, dict],
    *,
    infra: gpd.GeoDataFrame | None,
    kind: str,
    id_col: str,
    owner_col: str,
) -> tuple[dict[str, int], dict[str, list[dict]]]:
    """Turn infra-row-idx → parcel info into parcel_id → (count, summary).

    Each summary entry carries the infra side's identity (id/owner from
    the infra row, e.g. asr_number/owner_name for towers), matching what
    the single-shot ``ParcelHostsInfraJoin`` writes. Downstream consumers
    (e.g. ``DetailsPanel.svelte``) render the list of infrastructure on a
    parcel; the user wants the infra's identity, not the parcel's.
    """
    counts: dict[str, int] = {}
    summary: dict[str, list[dict]] = {}
    if infra is None or len(infra) == 0:
        return counts, summary
    for row_idx, attach in lookup.items():
        pid = attach.get("parcel_id_full")
        if pid is None or str(pid).strip() == "":
            continue
        pid = str(pid)
        counts[pid] = counts.get(pid, 0) + 1
        try:
            row = infra.loc[row_idx]
        except KeyError:
            continue
        summary.setdefault(pid, []).append(
            {
                "type": kind,
                "id": str(row.get(id_col) or ""),
                "owner": str(row.get(owner_col) or ""),
            }
        )
    return counts, summary


def _build_view_aggregators():
    """Build a list of streaming aggregators for the registered views."""
    out = []
    for v in all_views():
        if "parcel" not in v.inputs:
            continue
        agg = aggregator_for_view(v)
        if agg is not None:
            out.append(agg)
    return out


def _load_state_data(ctx: ComposeContext) -> list[str]:
    """Load every non-parcel canonical type for one state into ``ctx``.

    Skips parcel sources — parcels are read per-shard during the chunk
    loop. Returns the list of source_ids that contributed any rows.
    """
    sources_used: list[str] = []
    by_type: dict[str, list] = {}
    for n in all_normalizers():
        if "parcel" in n.canonical_types:
            # Parcel data is read per-shard during the chunk loop.
            continue
        try:
            per_source = n.load_state_data(ctx.state_fips)
        except Exception as e:  # noqa: BLE001
            log.warning("%s.load_state_data failed: %s", n.source_id, e)
            continue
        if not per_source:
            continue
        for ct, df in per_source.items():
            by_type.setdefault(ct, []).append(df)
        sources_used.append(n.source_id)
    for ct, frames in by_type.items():
        if ct in SPATIAL_TYPES:
            combined = gpd.GeoDataFrame(
                pd.concat(frames, ignore_index=True),
                geometry="geometry",
                crs="EPSG:4326",
            )
        else:
            combined = pd.concat(frames, ignore_index=True)
        ctx.set(ct, combined)
        log.info("  %s: %d rows (%d sources)", ct, len(combined), len(frames))
    # The parcel "source" itself: which parcel normalizers contributed
    # any shards for this state? We can probe normalized dirs cheaply.
    for n in all_normalizers():
        if "parcel" not in n.canonical_types:
            continue
        from . import NORMALIZED_ROOT

        src_dir = NORMALIZED_ROOT / n.source_id / OUTPUT_BASENAMES.get("parcel", "parcel")
        if src_dir.is_dir() and any(src_dir.glob("*.parquet")):
            sources_used.append(n.source_id)
    return sources_used
