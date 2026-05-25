"""Per-state Composer.

For one state FIPS, loads every canonical type from normalized/*,
filters to the state, runs all registered Joins (in dependency order),
runs all registered Views, and writes per-state outputs to
processed/composite/<state_fips>/.

Also generates catalog.json (self-documenting layer manifest) and
summary.json (counts only — quick read for the UI).
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
from .geographies import StateGeography
from .io import (
    dual_write_spatial,
    write_geojson,
    write_geoparquet,
    write_json,
    write_parquet,
)
from .manifest import get_raw_local_version

log = logging.getLogger("preprocess.compose")

# catalog.json schema version. Documented in ARCHITECTURE.md §6.
CATALOG_SCHEMA_VERSION = 3


@dataclass
class ComposeConfig:
    state: StateGeography
    force_rebuild: bool = False
    skip_views: list[str] = field(default_factory=list)
    skip_joins: list[str] = field(default_factory=list)


def compose(cfg: ComposeConfig) -> ComposeResult:
    state = cfg.state
    log.info("=== compose state %s (%s) ===", state.fips, state.name)
    ctx = ComposeContext(
        state_fips=state.fips,
        state_name=state.name,
        state_abbr=state.abbr,
    )

    # ── Load normalized data into the context ──────────────────────────
    sources_used = _load_state_data(ctx)
    log.info(
        "compose %s: loaded %d canonical types from %d sources",
        state.fips,
        len(ctx.tables),
        len(sources_used),
    )

    # ── Run joins in dependency order ──────────────────────────────────
    joins_applied: list[str] = []
    joins_skipped: list[str] = []
    for j in ordered_joins():
        if j.name in cfg.skip_joins:
            joins_skipped.append(j.name)
            log.info("skip join %s — disabled via config", j.name)
            continue
        if not j.is_applicable(ctx):
            joins_skipped.append(j.name)
            log.info("skip join %s — inputs missing", j.name)
            continue
        try:
            j.apply(ctx)
            joins_applied.append(j.name)
            log.info("✓ join %s", j.name)
        except Exception as e:
            log.error("✗ join %s failed: %s", j.name, e)
            ctx.warnings.append(f"join {j.name} failed: {e}")

    # ── Write per-canonical-type outputs ───────────────────────────────
    out_dir = COMPOSITE_ROOT / state.fips
    out_dir.mkdir(parents=True, exist_ok=True)
    views_dir = out_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)

    output_files: list[Path] = []
    counts: dict[str, int] = {}

    for ct, table in ctx.tables.items():
        if table is None or len(table) == 0:
            continue
        basename = OUTPUT_BASENAMES.get(ct, ct)
        if ct in SPATIAL_TYPES:
            write_simp = ct in {"parcel"}  # parcels are big enough to need simplified
            files, _ = dual_write_spatial(
                table,
                out_dir,
                basename,
                write_simplified_geojson=write_simp,
            )
            output_files.extend(files)
        else:
            p = out_dir / f"{basename}.parquet"
            write_parquet(table, p)
            output_files.append(p)
        counts[ct] = len(table)

    # ── Build views ────────────────────────────────────────────────────
    views_built: list[str] = []
    view_meta: dict[str, dict] = {}
    for v in all_views():
        if v.name in cfg.skip_views:
            continue
        if not v.is_applicable(ctx):
            continue
        try:
            result = v.build(ctx)
        except Exception as e:
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
                "geometry_type": _geom_type(result),
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
            # Tabular view
            write_parquet(
                result if isinstance(result, pd.DataFrame) else pd.DataFrame(result), p_parquet
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

    # ── catalog.json (self-documenting layer manifest) ─────────────────
    catalog = _build_catalog(state, ctx, view_meta, out_dir, sources_used)
    # Enforce the Python ↔ TS contract at write time. The map app's
    # parseCatalog assumes this shape; drift would surface as silent
    # missing layers in production. See catalog_schema.py.
    validate_catalog(catalog)
    catalog_path = out_dir / "catalog.json"
    write_json(catalog, catalog_path)
    output_files.append(catalog_path)

    # ── summary.json (quick stats) ─────────────────────────────────────
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
    }
    summary_path = out_dir / "summary.json"
    write_json(summary, summary_path)
    output_files.append(summary_path)

    log.info(
        "compose %s complete: %d sources, %d joins, %d views",
        state.fips,
        len(sources_used),
        len(joins_applied),
        len(views_built),
    )

    return ComposeResult(
        state_fips=state.fips,
        sources_used=sources_used,
        joins_applied=joins_applied,
        views_built=views_built,
        counts=counts,
        output_files=output_files,
    )


def _load_state_data(ctx: ComposeContext) -> list[str]:
    """Populate ``ctx.tables`` with every canonical type relevant to this state.

    Delegates per-source loading to :meth:`Normalizer.load_state_data` —
    the Composer no longer knows which sources shard their output, which
    have state_fips columns, or how to filter them. Each Normalizer's
    output is loaded behind its own interface; this function just
    iterates and concats across sources that produce the same
    canonical type.

    Returns the list of source_ids that contributed any rows.
    """
    sources_used: list[str] = []
    by_type: dict[str, list] = {}

    for n in all_normalizers():
        try:
            per_source = n.load_state_data(ctx.state_fips)
        except Exception as e:
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

    return sources_used


def _geom_type(gdf: gpd.GeoDataFrame) -> str:
    try:
        types = set(gdf.geom_type.dropna().unique())
        if not types:
            return ""
        return next(iter(types))
    except Exception:
        return ""


def _build_catalog(
    state: StateGeography,
    ctx: ComposeContext,
    view_meta: dict[str, dict],
    out_dir: Path,
    sources_used: list[str],
) -> dict:
    """Self-documenting layer manifest for the map app to consume."""
    layers: dict[str, dict] = {}
    for ct, table in ctx.tables.items():
        if table is None or len(table) == 0:
            continue
        basename = OUTPUT_BASENAMES.get(ct, ct)
        layer: dict = {
            "canonical_type": ct,
            "rows": len(table),
            "parquet_path": f"{basename}.parquet",
            "schema": _schema_summary(table),
        }
        if ct in SPATIAL_TYPES:
            layer["geometry_type"] = _geom_type(table)
            # Advertise a GeoJSON path only when the file was actually
            # written — huge layers (parcels) are Parquet-only.
            if (out_dir / f"{basename}.geojson").exists():
                layer["geojson_path"] = f"{basename}.geojson"
            if (out_dir / f"{basename}.simplified.geojson").exists():
                layer["simplified_geojson_path"] = f"{basename}.simplified.geojson"
        layers[basename] = layer

    # Lineage: which raw version of each source fed this composite. Lets us
    # answer "what raw vintages produced this state?" without parsing logs.
    sources_used_versions = {
        sid: get_raw_local_version(sid) for sid in sorted(sources_used)
    }

    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "state_fips": state.fips,
        "state_name": state.name,
        "state_abbr": state.abbr,
        "generated_at": utcnow_iso(),
        "layers": layers,
        "views": view_meta,
        "sources_used_versions": sources_used_versions,
    }


def _schema_summary(table) -> dict:
    """Light schema summary — col name → dtype string."""
    out: dict[str, str] = {}
    for col in getattr(table, "columns", []):
        if col == getattr(table, "_geometry_column_name", "geometry"):
            continue
        try:
            out[str(col)] = str(table[col].dtype)
        except Exception:
            out[str(col)] = "unknown"
    return out
