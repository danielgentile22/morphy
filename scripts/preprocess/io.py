"""I/O helpers: dual-write GeoParquet + GeoJSON; chunked Parquet reader;
simplified-geojson writer; raw.parquet preservation.

Conventions:
  - All output GeoDataFrames are in EPSG:4326.
  - Parquet writes use pyarrow (the default geopandas backend).
  - GeoJSON writes coerce datetimes to ISO strings so JSON serialization
    doesn't choke.
  - Derivative columns (geom_centroid, geom_bbox, geom_simplified) are
    written to Parquet but NOT to GeoJSON — GeoJSON keeps only the primary
    geometry to stay lean for browsers.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path

import geopandas as gpd
import pandas as pd

log = logging.getLogger("preprocess.io")

# Columns to strip before writing GeoJSON (kept in Parquet).
_GEOJSON_DROP_COLS = {"geom_centroid", "geom_bbox", "geom_simplified"}


def _prep_complex_cols(df):
    """JSON-encode dict / list cell values so Parquet doesn't choke on
    empty structs or heterogeneous nested types. Returns a shallow copy.

    Operates on object-dtype columns only. Scalars and strings pass through
    untouched. ``bbox`` lists, ``extras`` dicts, ``infrastructure_summary``
    lists, etc. all become JSON strings on disk and are decoded on read.
    """
    df = df.copy()
    for col in df.columns:
        if col == getattr(df, "_geometry_column_name", "geometry"):
            continue
        if df[col].dtype != object:
            continue
        # Inspect a sample to decide if this column carries complex types.
        sample = df[col].dropna().head(50)
        if sample.empty:
            continue
        if not any(isinstance(v, (dict, list)) for v in sample):
            continue

        def _encode(v):
            if v is None:
                return None
            if isinstance(v, (dict, list)):
                return json.dumps(v, default=str)
            return v

        df[col] = df[col].map(_encode)
    return df


def write_geoparquet(gdf: gpd.GeoDataFrame, path: Path) -> int:
    """Write a GeoDataFrame to Parquet. Returns the file size in bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    g = _prep_complex_cols(gdf)
    # geopandas writes GeoParquet by default since 0.13.
    g.to_parquet(path, index=False)
    return path.stat().st_size


def write_parquet(df: pd.DataFrame, path: Path) -> int:
    """Write a plain DataFrame to Parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    df = _prep_complex_cols(df)
    df.to_parquet(path, index=False)
    return path.stat().st_size


def write_geojson(
    gdf: gpd.GeoDataFrame,
    path: Path,
    *,
    use_simplified_geometry: bool = False,
) -> int:
    """Write a GeoDataFrame to GeoJSON. Drops geometry-derivative columns.

    If use_simplified_geometry is True, the file uses geom_simplified as the
    primary geometry (must exist on the GDF).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    g = gdf.copy()
    if use_simplified_geometry:
        if "geom_simplified" not in g.columns:
            raise ValueError("use_simplified_geometry=True but geom_simplified column missing")
        g = g.set_geometry("geom_simplified", drop=True, crs=g.crs or "EPSG:4326")

    drop = [c for c in g.columns if c in _GEOJSON_DROP_COLS and c != g.geometry.name]
    if drop:
        g = g.drop(columns=drop)

    # GeoJSON can't serialize bbox JSON lists with shapely objects in cells —
    # coerce non-string cells in object columns to JSON strings.
    for col in g.columns:
        if col == g.geometry.name:
            continue
        if pd.api.types.is_datetime64_any_dtype(g[col]):
            g[col] = g[col].astype("string")

    g.to_file(path, driver="GeoJSON")
    return path.stat().st_size


# Above this row count, skip the full GeoJSON (only write simplified) —
# 100K polygons or 500K points produces a >100 MB GeoJSON that hangs the
# browser anyway, and Parquet remains the canonical format for analysis.
HUGE_GEOJSON_THRESHOLD = 100_000


def dual_write_spatial(
    gdf: gpd.GeoDataFrame,
    out_dir: Path,
    basename: str,
    *,
    write_simplified_geojson: bool = False,
    skip_full_geojson_if_huge: bool = True,
) -> tuple[list[Path], int]:
    """Write {basename}.parquet plus GeoJSON variant(s). Returns (files, bytes).

    For huge layers (rows ≥ HUGE_GEOJSON_THRESHOLD), the full GeoJSON is
    skipped because browsers can't load it anyway — only the simplified
    version is written. Parquet always wins for analytical use.
    """
    written: list[Path] = []
    total = 0

    parquet_path = out_dir / f"{basename}.parquet"
    total += write_geoparquet(gdf, parquet_path)
    written.append(parquet_path)

    is_huge = skip_full_geojson_if_huge and len(gdf) >= HUGE_GEOJSON_THRESHOLD
    if not is_huge:
        geojson_path = out_dir / f"{basename}.geojson"
        total += write_geojson(gdf, geojson_path)
        written.append(geojson_path)

    if (write_simplified_geojson or is_huge) and "geom_simplified" in gdf.columns:
        # For huge layers the "primary" public file is the simplified one.
        simp_path = out_dir / (
            f"{basename}.geojson" if is_huge else f"{basename}.simplified.geojson"
        )
        total += write_geojson(gdf, simp_path, use_simplified_geometry=True)
        written.append(simp_path)

    return written, total


def write_raw_parquet(df, out_dir: Path, *, name: str = "raw.parquet") -> int:
    """Write full-fidelity raw data as Parquet (Stage A preservation).

    Accepts either a DataFrame or a GeoDataFrame. Column names that are
    invalid for Parquet (empty, contain '/' etc.) are sanitized.
    """
    if df is None or len(df) == 0:
        return 0

    df = df.copy()
    df.columns = [_sanitize_col(c) for c in df.columns]

    path = out_dir / name
    out_dir.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    df = _prep_complex_cols(df)
    if isinstance(df, gpd.GeoDataFrame) and df.geometry is not None:
        df.to_parquet(path, index=False)
    else:
        # Force a plain DataFrame even if originally a GeoDataFrame with no geom.
        pd.DataFrame(df).to_parquet(path, index=False)
    return path.stat().st_size


def _sanitize_col(name) -> str:
    """Make a column name safe for Parquet."""
    s = str(name).strip()
    if not s:
        return "_unnamed"
    return s.replace("/", "_").replace(".", "_")


def read_geoparquet(path: Path, *, columns: Iterable[str] | None = None) -> gpd.GeoDataFrame:
    """Read GeoParquet, optionally with column projection."""
    if columns is not None:
        cols = list(columns)
        if "geometry" not in cols:
            cols = cols + ["geometry"]
        return gpd.read_parquet(path, columns=cols)
    return gpd.read_parquet(path)


def read_parquet(path: Path, *, columns: Iterable[str] | None = None) -> pd.DataFrame:
    """Read plain Parquet, optionally with column projection."""
    if columns is not None:
        return pd.read_parquet(path, columns=list(columns))
    return pd.read_parquet(path)


def write_json(payload: dict, path: Path) -> int:
    """Write a JSON file (UTF-8, pretty-printed, sorted keys)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(text)
    return path.stat().st_size
