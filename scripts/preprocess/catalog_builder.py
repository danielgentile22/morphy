"""Build the per-state ``catalog.json`` artifact.

A small layer between the compose paths and the catalog JSON schema:
both single-shot and chunked compose call ``build_catalog`` to produce
the manifest, so the shape stays identical regardless of which path
ran. The chunked path additionally passes ``sharded_parcels`` to
advertise the parcel layer as a directory of shards instead of a single
file.

Schema: ``schemas/catalog.schema.json``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd

from .base import (
    OUTPUT_BASENAMES,
    SPATIAL_TYPES,
    ComposeContext,
    utcnow_iso,
)
from .geographies import StateGeography
from .manifest import get_raw_local_version

# catalog.json schema version. Documented in ARCHITECTURE.md §6.
CATALOG_SCHEMA_VERSION = 3


def geom_type(gdf: gpd.GeoDataFrame) -> str:
    """Single geometry type advertised for a layer (best-effort).

    Returns the first unique non-null geom_type, or "" if the table has
    no geometry / empty / heterogeneous mix.
    """
    try:
        types = set(gdf.geom_type.dropna().unique())
        if not types:
            return ""
        return next(iter(types))
    except Exception:
        return ""


def schema_summary(table) -> dict[str, str]:
    """Light schema summary — column name → dtype string."""
    out: dict[str, str] = {}
    for col in getattr(table, "columns", []):
        if col == getattr(table, "_geometry_column_name", "geometry"):
            continue
        try:
            out[str(col)] = str(table[col].dtype)
        except Exception:
            out[str(col)] = "unknown"
    return out


def build_catalog(
    state: StateGeography,
    ctx: ComposeContext,
    view_meta: dict[str, dict],
    out_dir: Path,
    sources_used: list[str],
    *,
    sharded_parcels: dict[str, Any] | None = None,
) -> dict:
    """Self-documenting layer manifest for the map app to consume.

    ``sharded_parcels`` is the chunked-compose override: when set, the
    parcel layer is advertised as a directory of shards (the dict
    carries ``rows``, ``schema``, ``geometry_type``, ``shard_count``)
    and the parcel entry in ``ctx.tables`` is skipped from the standard
    loop. When ``None``, the parcel layer is built from ``ctx.tables``
    like any other canonical type.
    """
    layers: dict[str, dict] = {}

    if sharded_parcels is not None:
        parcel_basename = OUTPUT_BASENAMES.get("parcel", "parcel")
        layers[parcel_basename] = {
            "canonical_type": "parcel",
            "rows": sharded_parcels["rows"],
            "parquet_path": parcel_basename,  # directory, not a file
            "schema": sharded_parcels["schema"],
            "geometry_type": sharded_parcels["geometry_type"],
            "sharded": True,
            "shard_count": sharded_parcels["shard_count"],
        }

    for ct, table in ctx.tables.items():
        if sharded_parcels is not None and ct == "parcel":
            continue
        if table is None or len(table) == 0:
            continue
        basename = OUTPUT_BASENAMES.get(ct, ct)
        layer: dict = {
            "canonical_type": ct,
            "rows": len(table),
            "parquet_path": f"{basename}.parquet",
            "schema": schema_summary(table),
        }
        if ct in SPATIAL_TYPES:
            layer["geometry_type"] = geom_type(table)
            # Advertise a GeoJSON path only when the file was actually
            # written — huge layers (parcels) are Parquet-only.
            if (out_dir / f"{basename}.geojson").exists():
                layer["geojson_path"] = f"{basename}.geojson"
            if (out_dir / f"{basename}.simplified.geojson").exists():
                layer["simplified_geojson_path"] = f"{basename}.simplified.geojson"
        layers[basename] = layer

    # Lineage: which raw version of each source fed this composite.
    # Coerce None → "" so the catalog-schema string-type contract stays
    # strict on shape but tolerant of sources without a recorded version
    # (fixture sources in tests, or a source pre-manifest-record).
    sources_used_versions = {
        sid: (get_raw_local_version(sid) or "") for sid in sorted(set(sources_used))
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
