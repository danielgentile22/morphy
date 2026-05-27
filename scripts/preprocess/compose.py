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
  2. **Owner-cluster pre-pass** — scan every parcel shard, projecting
     to owner-related columns only. Compute cluster_id + sizes +
     value totals across the whole state. Store the parcel_id_full →
     cluster lookup.
  3. **Tower-to-parcel pre-pass** — iterate parcel shards, sjoin each
     chunk against the (small) tower table, accumulate tower → parcel
     matches. Apply to the tower table after the loop.
  4. Same pre-pass for solar / billboard sjoins.
  5. **Per-chunk loop** — for each parcel shard:
        a. Run parcel-touching joins (ParcelHostsInfra,
           CountyScoreToParcel, ParcelToDistress, OwnerCluster from
           lookup, InterestingnessScore).
        b. Feed the annotated chunk to every streaming view aggregator.
        c. Write `composite/<fips>/parcels/<label>.parquet`.
  6. Run non-parcel-touching joins on towers / solar / billboard.
  7. Finalize view aggregators; write view outputs + catalog.

Joins that don't fit the chunked pattern (e.g. arbitrary new joins
declared by a future contributor) are skipped with a warning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import COMPOSITE_ROOT
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
from .catalog_schema import validate_catalog
from .compose_helpers import (
    aggregator_for_view,
    iter_state_parcel_shards,
    iter_state_parcel_shards_columns,
)
from .cluster import cluster_id, normalize_address, normalize_owner_name
from .geographies import StateGeography
from .per_chunk_joins import (
    apply_county_score,
    apply_interestingness_score,
    apply_parcel_hosts_infra,
    apply_parcel_to_distress,
    attach_owner_cluster,
)
from .io import (
    dual_write_spatial,
    write_geojson,
    write_geoparquet,
    write_json,
    write_parquet,
)
from .catalog_builder import build_catalog, geom_type, schema_summary

log = logging.getLogger("preprocess.compose")


@dataclass
class ComposeConfig:
    state: StateGeography
    skip_views: list[str] = field(default_factory=list)
    skip_joins: list[str] = field(default_factory=list)


# ── Owner-cluster pre-pass ────────────────────────────────────────────────


def _build_owner_cluster_lookup(state_fips: str) -> pd.DataFrame:
    """Scan every parcel shard for owner columns; emit cluster-keyed totals.

    Returns a DataFrame indexed by ``owner_cluster_id`` with columns
    ``owner_cluster_size`` and ``owner_cluster_value_total`` — one row
    per distinct cluster (so the index is always unique, even when the
    underlying parcel_id_full has duplicates across shards — FL FDOR NAL
    has these because PARCEL_ID is county-unique, not state-unique).

    Per-row ``owner_cluster_id`` is recomputed by ``attach_owner_cluster``
    on the chunk itself (the same per-row formula `OwnerClusterJoin`
    uses) — this lookup only supplies the global aggregates that need
    a whole-state pass.

    Memory bounded to one shard's owner columns at any time (~tens of MB
    for an 11 M-parcel state, vs the full ~13 GB if loaded whole).
    """
    cluster_rows: list[pd.DataFrame] = []
    owner_cols = [
        "owner_name_norm",
        "mailing_addr_norm",
        "owner_name",
        "mailing_addr",
        "assessed_value",
    ]
    for _label, df in iter_state_parcel_shards_columns(state_fips, owner_cols):
        # Some shards may not carry the *_norm columns — fall back to
        # normalising on the fly so we never crash a state because one
        # source skipped normalisation.
        owner_norm = (
            df["owner_name_norm"]
            if "owner_name_norm" in df.columns
            else df.get("owner_name", "").map(normalize_owner_name)
        )
        addr_norm = (
            df["mailing_addr_norm"]
            if "mailing_addr_norm" in df.columns
            else df.get("mailing_addr", "").map(normalize_address)
        )
        cluster_rows.append(
            pd.DataFrame(
                {
                    "owner_cluster_id": [
                        cluster_id(o, a) for o, a in zip(owner_norm, addr_norm)
                    ],
                    "assessed_value": pd.to_numeric(
                        df.get("assessed_value", 0), errors="coerce"
                    ).fillna(0.0),
                }
            )
        )
    if not cluster_rows:
        return pd.DataFrame(
            columns=["owner_cluster_size", "owner_cluster_value_total"],
            index=pd.Index([], name="owner_cluster_id"),
        )
    all_owners = pd.concat(cluster_rows, ignore_index=True)
    # Cluster size / value totals across the whole state. Parcels with no
    # clusterable owner/address (cluster_id == "") are excluded from the
    # aggregate but still default to size=1, value=0 when attached.
    non_empty = all_owners[all_owners["owner_cluster_id"] != ""]
    if len(non_empty) == 0:
        return pd.DataFrame(
            columns=["owner_cluster_size", "owner_cluster_value_total"],
            index=pd.Index([], name="owner_cluster_id"),
        )
    agg = (
        non_empty.groupby("owner_cluster_id")
        .agg(
            owner_cluster_size=("owner_cluster_id", "size"),
            owner_cluster_value_total=("assessed_value", "sum"),
        )
    )
    agg["owner_cluster_size"] = agg["owner_cluster_size"].astype(int)
    agg["owner_cluster_value_total"] = agg["owner_cluster_value_total"].astype(float)
    return agg  # index = owner_cluster_id (unique)


# ── Tower / solar / billboard pre-pass (sjoin against parcel shards) ──────


def _build_infra_to_parcel_lookup(
    infra: gpd.GeoDataFrame,
    state_fips: str,
    *,
    keep_cols: list[str],
) -> dict[int, dict]:
    """For each row of `infra`, find the parcel it intersects (any shard).

    Returns a dict: infra row index → dict of parcel columns to attach
    (parcel_id_full, parcel_owner, parcel_value, parcel_acreage,
    parcel_use_code — whichever exist on parcels). Empty when infra has
    no matches or no geometry.

    The sjoin runs once per shard, so peak memory stays bounded to one
    shard's parcel geometry plus the (small) infra geometry.
    """
    if infra is None or len(infra) == 0:
        return {}
    out: dict[int, dict] = {}
    infra_geo = infra[["geometry"]].reset_index()
    for _label, chunk in iter_state_parcel_shards(state_fips):
        present = [c for c in keep_cols if c in chunk.columns]
        if "geometry" not in chunk.columns:
            continue
        right = chunk[[*present, "geometry"]].rename(
            columns={
                "owner_name": "parcel_owner",
                "assessed_value": "parcel_value",
                "acreage": "parcel_acreage",
                "land_use_code": "parcel_use_code",
            }
        )
        try:
            hit = gpd.sjoin(infra_geo, right, how="inner", predicate="within")
        except Exception as e:  # noqa: BLE001 — bad shard mustn't kill the loop
            log.warning("infra→parcel sjoin failed on a shard: %s", e)
            continue
        for row in hit.itertuples(index=False):
            row_d = row._asdict() if hasattr(row, "_asdict") else dict(row)
            idx = int(row_d.get("index", -1))
            if idx < 0:
                continue
            # Skip the sjoin index_right + the geometry column
            attach = {
                k: v
                for k, v in row_d.items()
                if k
                not in {"index", "index_right", "geometry"}
            }
            # First match wins — a tower in two overlapping parcels is rare
            # and `compose` today doesn't disambiguate either.
            out.setdefault(idx, attach)
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
        infra[col] = infra.index.map(lambda i: lookup.get(int(i), {}).get(col))
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
    log.info("owner-cluster pre-pass — scanning shards for owner columns…")
    owner_lookup = _build_owner_cluster_lookup(state.fips)
    log.info("owner-cluster pre-pass: %d parcels indexed", len(owner_lookup))

    # 3-4. Infra→parcel pre-pass --------------------------------------------
    log.info("infra→parcel sjoin pre-pass…")
    tower_lookup = _build_infra_to_parcel_lookup(
        ctx.get("tower"),
        state.fips,
        keep_cols=[
            "parcel_id_full",
            "owner_name",
            "assessed_value",
            "acreage",
            "land_use_code",
        ],
    )
    solar_lookup = _build_infra_to_parcel_lookup(
        ctx.get("solar_facility"),
        state.fips,
        keep_cols=["parcel_id_full", "owner_name"],
    )
    billboard_lookup = _build_infra_to_parcel_lookup(
        ctx.get("billboard"),
        state.fips,
        keep_cols=["parcel_id_full", "owner_name"],
    )
    log.info(
        "infra→parcel lookups: towers=%d, solar=%d, billboards=%d",
        len(tower_lookup),
        len(solar_lookup),
        len(billboard_lookup),
    )

    # 5. Build per-parcel reverse maps (parcel_id_full → infra counts +
    #    summary list) from the lookups built above. This replaces the
    #    iter-over-infra-rows logic of ParcelHostsInfraJoin without
    #    needing a single in-memory parcel table.
    tower_counts, tower_summary = _reverse_index(
        tower_lookup, infra=ctx.get("tower"), kind="tower",
        id_col="asr_number", owner_col="owner_name",
    )
    solar_counts, solar_summary = _reverse_index(
        solar_lookup, infra=ctx.get("solar_facility"), kind="solar",
        id_col="facility_id", owner_col="operator",
    )
    billboard_counts, billboard_summary = _reverse_index(
        billboard_lookup, infra=ctx.get("billboard"), kind="billboard",
        id_col="permit_no", owner_col="owner",
    )

    # 6. Per-chunk loop -----------------------------------------------------
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
            chunk, tower_counts, solar_counts, billboard_counts, tower_summary, solar_summary, billboard_summary
        )
        chunk = apply_county_score(chunk, ctx.get("county_score"))
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

    log.info(
        "chunk loop done: %d shards, %d parcels", shard_count, total_parcel_rows
    )

    # 7. Apply infra→parcel lookups onto the in-memory infra tables, then
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

    # 8. Write non-parcel canonical-type outputs (towers, solar, billboard,
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

    # 9. Finalize streaming views + run non-streaming views in-memory.
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

    # 10. Catalog + summary (sharded layer descriptor for parcels).
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


