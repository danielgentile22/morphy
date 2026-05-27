"""State-parcel normalizer + the shared streaming driver.

Every state's parcel feed maps to the same canonical schema; only the
column names differ. Each upstream feed gets one ``ParcelAdapter``
constant under :mod:`preprocess.normalizers.state_parcel_adapters`, and
the shared driver :func:`normalize_state_parcels` does the actual work.

Importing this module triggers ``register_normalizer_instance`` for
every adapter, so the rest of the pipeline (Composer, CLI, UI) sees one
Normalizer per ``source_id`` just as before.

Adding a new parcel source:

  1. Create ``state_parcel_adapters/<state>.py`` exporting one
     ``ParcelAdapter`` constant. See ``state_parcel_adapters/ar.py`` for
     the minimal shape and ``mt.py`` for the optional ``county_resolver``.
  2. Import it below and pass it to ``_register``.

Pipeline:

  raw layer  →  raw parquet                (full fidelity)
            →  map_layer_to_canonical()    (vectorized, adapter-driven)
            →  geometry-valid filter
            →  add_polygon_derivatives
            →  add_system_columns
            →  per-layer canonical parquet under ``parcels/``

Peak memory stays bounded to a single layer so FL's 67-county / ~10 M-parcel
PAR set works on a 16 GB machine (ADR-050).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import geopandas as gpd
import pandas as pd

from ..base import (
    Normalizer,
    NormalizeResult,
    add_system_columns,
    quality_report,
    register_normalizer_instance,
    write_quality_report,
)
from ..cluster import infer_owner_kind, normalize_address, normalize_owner_name
from ..geom import add_polygon_derivatives
from ..io import write_geoparquet, write_raw_parquet
from .fips import canon_county_fips, state_fips_from_county_fips
from .pandas_coerce import safe_str

if TYPE_CHECKING:
    pass

log = logging.getLogger("preprocess.state_parcels")


# ── Adapter dataclass + Normalizer ───────────────────────────────────────


CountyResolver = Callable[[str], "str | None"]
PostMap = Callable[["gpd.GeoDataFrame"], "gpd.GeoDataFrame"]


@dataclass(frozen=True)
class ParcelAdapter:
    """Per-source description for the shared parcel-normalize driver.

    Attributes:
        source_id: The fetch-side ``DataSource.id`` this adapter describes.
        state_fips: Two-digit state FIPS hint, used when the raw county
            column doesn't carry the state prefix (e.g. MT has only county
            names; AR has a 3-digit county code).
        field_map: Canonical-name → list of candidate raw column names;
            first match wins. See ``map_layer_to_canonical`` for the
            canonical-field vocabulary.
        county_resolver: Optional callable taking a raw county value and
            returning a 5-digit county FIPS (or None if it can't resolve).
            Used when the raw field is a county *name* rather than a FIPS
            (e.g. MT Cadastral's ``CountyName``). When None, the driver
            falls back to ``canon_county_fips``.
        post_map: Optional escape hatch — runs after the default
            canonical mapping. Receives the canonical GeoDataFrame and
            returns the (possibly mutated) GeoDataFrame. Reserve for
            quirks that can't be expressed via ``field_map`` alone.
    """

    source_id: str
    state_fips: str
    field_map: dict[str, list[str]]
    county_resolver: CountyResolver | None = None
    post_map: PostMap | None = None


class ParcelNormalizer(Normalizer):
    """Concrete Normalizer that delegates to the shared parcel driver.

    One instance per ParcelAdapter — registered via
    ``register_normalizer_instance(ParcelNormalizer(ADAPTER))``.
    """

    canonical_types = ["parcel"]

    def __init__(self, adapter: ParcelAdapter) -> None:
        self.adapter = adapter
        self.source_id = adapter.source_id

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        return normalize_state_parcels(raw_dir, out_dir, self.adapter)


# ── Column helpers (vectorized) ──────────────────────────────────────────


def _resolve_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """First candidate column actually present in df, else None."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _str_series(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    """Cleaned-string Series for the first matching column; all-'' if none match."""
    col = _resolve_col(df, candidates)
    if col is None:
        return pd.Series("", index=df.index, dtype="object")
    return df[col].map(safe_str)


def _num_series(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    """Numeric (float64, NaN for nulls) Series for the first matching column."""
    col = _resolve_col(df, candidates)
    if col is None:
        return pd.Series(float("nan"), index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce")


def _join_nonempty(parts: list[pd.Series], sep: str = ", ") -> pd.Series:
    """Row-wise join of cleaned-string Series, skipping blanks. Fully vectorized
    (replaces a per-row combine_address call)."""
    acc = pd.Series("", index=parts[0].index, dtype="object")
    for p in parts:
        p = p.fillna("").astype(str)
        need_sep = (acc.str.len() > 0) & (p.str.len() > 0)
        acc = acc.str.cat(need_sep.map({True: sep, False: ""}).str.cat(p))
    return acc


def _map_unique(series: pd.Series, fn) -> pd.Series:
    """Apply a scalar function via a unique-value lookup. For columns with
    heavy repetition (owner names, FIPS codes, addresses) this calls `fn`
    once per distinct value instead of once per row."""
    lookup = {v: fn(v) for v in series.unique()}
    return series.map(lookup)


# ── Layer readers (multi-format, streaming) ──────────────────────────────


def _to_4326(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame | None:
    """Reproject one layer to EPSG:4326. Returns None if reprojection fails."""
    if g.crs is None:
        log.warning("  layer has no CRS — assuming EPSG:4326")
        return g.set_crs("EPSG:4326")
    if g.crs.to_epsg() != 4326:
        try:
            return g.to_crs("EPSG:4326")
        except Exception as e:
            log.warning("  reproject failed (%s); skipping layer", e)
            return None
    return g


def _iter_multi_layer(path: Path):
    """Yield (layer_name, GeoDataFrame) for each layer in a .gpkg / .gdb.

    pyogrio.list_layers returns an ndarray of [name, geometry_type] rows.
    """
    try:
        import pyogrio

        layers = pyogrio.list_layers(path)
    except Exception as e:
        log.warning("  failed to list layers in %s: %s", path, e)
        return
    names: list[str] = []
    try:
        for li in layers:
            if hasattr(li, "__len__") and len(li) > 0 and not isinstance(li, str):
                names.append(str(li[0]))
            else:
                names.append(str(li))
    except Exception:
        try:
            for i in range(layers.shape[0]):
                names.append(str(layers[i, 0]))
        except Exception as e:
            log.warning("  couldn't parse layers from %s: %s", path, e)
            return
    for lname in names:
        try:
            # on_invalid="fix" repairs unclosed LinearRings rather than
            # letting GEOS abort the whole layer read (see _iter_raw_layers).
            g = gpd.read_file(path, layer=lname, on_invalid="fix")
            log.info("  read %s::%s: %d rows", path.name, lname, len(g))
            yield lname, g
        except Exception as e:
            log.warning("  failed to read %s::%s: %s", path.name, lname, e)


def _iter_raw_layers(raw_dir: Path):
    """Yield (label, GeoDataFrame) for every parcel layer under raw_dir, one
    at a time, reprojected to EPSG:4326.

    Streaming — only one layer is held at a time. Materialising every layer
    before concatenating would need ~50 GB peak for FL's 67-county / ~28 GB
    FDOR set; this generator keeps peak memory bounded to a single county.
    """
    for shp in sorted(raw_dir.rglob("*.shp")):
        # Some FDOR county exports ship a *directory* named `<county>.shp`
        # (e.g. leon_2025par.shp); rglob matches it but it's not a shapefile.
        if not shp.is_file():
            log.info("  skip %s — directory with a .shp suffix, not a shapefile", shp.name)
            continue
        try:
            # on_invalid="fix" repairs polygons with unclosed rings instead
            # of aborting the read (5 FDOR counties trip GEOS otherwise).
            g = gpd.read_file(shp, on_invalid="fix")
        except Exception as e:
            log.warning("  failed to read %s: %s", shp, e)
            continue
        log.info("  read shapefile %s: %d rows", shp.relative_to(raw_dir), len(g))
        g = _to_4326(g)
        if g is not None:
            yield shp.stem, g
    for gpkg in sorted(raw_dir.rglob("*.gpkg")):
        for lname, g in _iter_multi_layer(gpkg):
            g = _to_4326(g)
            if g is not None:
                yield f"{gpkg.stem}_{lname}", g
    for gdb in sorted(p for p in raw_dir.rglob("*.gdb") if p.is_dir()):
        for lname, g in _iter_multi_layer(gdb):
            g = _to_4326(g)
            if g is not None:
                yield f"{gdb.stem}_{lname}", g
    for gj in sorted(raw_dir.rglob("*.geojson")):
        try:
            g = gpd.read_file(gj, on_invalid="fix")
        except Exception as e:
            log.warning("  failed to read %s: %s", gj, e)
            continue
        log.info("  read geojson %s: %d rows", gj.name, len(g))
        g = _to_4326(g)
        if g is not None:
            yield gj.stem, g


# ── Canonical mapping (adapter-driven) ───────────────────────────────────


def map_layer_to_canonical(
    g: gpd.GeoDataFrame,
    adapter: ParcelAdapter,
) -> gpd.GeoDataFrame:
    """Map one raw parcel layer to the canonical narrow schema.

    Vectorized — every canonical column is a column-wise operation; the
    three regex-heavy scalar functions (infer_owner_kind,
    normalize_owner_name, normalize_address) run once per *distinct* value.
    Returns the narrow GeoDataFrame *before* the geometry-validity filter.
    """
    fm = adapter.field_map
    n = len(g)

    owner_name = _str_series(g, fm.get("owner_name", []))
    mailing_addr = _join_nonempty(
        [
            _str_series(g, fm.get("mailing_addr", [])),
            _str_series(g, fm.get("mailing_city", [])),
            _str_series(g, fm.get("mailing_state", [])),
            _str_series(g, fm.get("mailing_zip", [])),
        ]
    )
    parcel_id_full = _str_series(g, fm.get("parcel_id_full", []))

    county_raw = _str_series(g, fm.get("county_fips", []))
    if adapter.county_resolver is not None:
        # Source identifies counties by name (e.g. MT Cadastral).
        county_fips = _map_unique(county_raw, adapter.county_resolver)
    else:
        county_fips = _map_unique(
            county_raw, lambda v: canon_county_fips(v, state_fips=adapter.state_fips)
        )
    state_fips = _map_unique(
        county_fips, lambda v: state_fips_from_county_fips(v) or adapter.state_fips
    )

    out = pd.DataFrame(index=g.index)
    out["parcel_id"] = _str_series(g, fm.get("parcel_id", []))
    out["parcel_id_full"] = parcel_id_full
    out["owner_name"] = owner_name
    out["owner_name_2"] = _str_series(g, fm.get("owner_name_2", []))
    out["owner_kind"] = _map_unique(owner_name, infer_owner_kind)
    out["owner_name_norm"] = _map_unique(owner_name, normalize_owner_name)
    out["mailing_addr"] = mailing_addr
    out["mailing_addr_norm"] = _map_unique(mailing_addr, normalize_address)
    out["mailing_city"] = _str_series(g, fm.get("mailing_city", []))
    out["mailing_state"] = _str_series(g, fm.get("mailing_state", []))
    out["mailing_zip"] = _str_series(g, fm.get("mailing_zip", []))
    out["situs_addr"] = _str_series(g, fm.get("situs_addr", []))
    out["situs_city"] = _str_series(g, fm.get("situs_city", []))
    out["situs_state"] = None
    out["situs_zip"] = None
    out["acreage"] = _num_series(g, fm.get("acreage", []))
    out["land_value"] = _num_series(g, fm.get("land_value", []))
    out["improvement_value"] = _num_series(g, fm.get("improvement_value", []))
    out["assessed_value"] = _num_series(g, fm.get("assessed_value", []))
    out["land_use_code"] = _str_series(g, fm.get("land_use_code", []))
    out["land_use_desc"] = _str_series(g, fm.get("land_use_desc", []))
    out["year_built"] = _num_series(g, fm.get("year_built", []))
    out["county_fips"] = county_fips
    out["state_fips"] = state_fips
    # Reverse-summary columns initialised as placeholders; the Composer's
    # joins (ParcelHostsInfraJoin, CountyScoreToParcelJoin, …) populate them.
    out["extras"] = [{} for _ in range(n)]
    out["has_tower"] = False
    out["tower_count"] = 0
    out["has_solar"] = False
    out["solar_count"] = 0
    out["has_billboard"] = False
    out["billboard_count"] = 0
    out["infrastructure_summary"] = [[] for _ in range(n)]
    out["in_oz"] = False
    out["in_qct"] = False
    out["distress_overlays"] = [[] for _ in range(n)]
    out["distress_tier"] = ""
    out["persistent_poverty"] = False
    out["interestingness_score"] = 0.0
    out["interestingness_components"] = [{} for _ in range(n)]
    out["owner_cluster_id"] = ""
    out["owner_cluster_size"] = 0
    out["owner_cluster_value_total"] = 0.0
    out["_source_row_id"] = parcel_id_full
    out["geometry"] = g.geometry.values

    return gpd.GeoDataFrame(out, geometry="geometry", crs="EPSG:4326")


# ── Driver entry point ───────────────────────────────────────────────────


def normalize_state_parcels(
    raw_dir: Path,
    out_dir: Path,
    adapter: ParcelAdapter,
) -> NormalizeResult:
    """Streaming per-layer normalize for one parcel source.

    Each input layer (county shapefile, GeoJSON page, gdb layer) is read,
    mapped to the canonical schema, geometry-filtered, and written to its
    own ``parcels/<label>.parquet`` — a standard multi-file parquet
    dataset the Composer reads back. Peak memory stays bounded to a single
    layer (ADR-050).
    """
    owner_cols = adapter.field_map.get("owner_name", [])
    # A source with no declared owner column maps every layer; otherwise
    # only layers carrying an owner column are parcels (skips e.g. MT's
    # PLSS / water shapefiles).
    map_all = not owner_cols

    parcels_dir = out_dir / "parcels"
    raw_dir_out = out_dir / "raw"
    for d in (parcels_dir, raw_dir_out):
        if d.exists():
            for old in d.glob("*.parquet"):
                old.unlink()
        d.mkdir(parents=True, exist_ok=True)

    raw_bytes = 0
    canon_bytes = 0
    raw_row_total = 0
    canon_row_total = 0
    dropped_total = 0
    n_layers_seen = 0
    n_layers_mapped = 0
    states_covered: set[str] = set()
    output_files: list[Path] = []
    qr_sample_raw: gpd.GeoDataFrame | None = None
    qr_sample_parcels: gpd.GeoDataFrame | None = None

    for label, g in _iter_raw_layers(raw_dir):
        n_layers_seen += 1
        if not (map_all or any(c in g.columns for c in owner_cols)):
            log.info(
                "  %s: skip layer %s — no owner column (not a parcel layer)",
                adapter.source_id,
                label,
            )
            continue
        n_layers_mapped += 1
        raw_row_total += len(g)
        safe_label = re.sub(r"[^A-Za-z0-9_.-]", "_", label)

        raw_bytes += write_raw_parquet(g, raw_dir_out, name=f"{safe_label}.parquet")
        if qr_sample_raw is None:
            qr_sample_raw = g

        gdf = map_layer_to_canonical(g, adapter)
        del g  # free the wide raw frame before the next layer

        n_before = len(gdf)
        gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid].copy()
        dropped_total += n_before - len(gdf)

        gdf = add_polygon_derivatives(gdf)
        gdf = add_system_columns(gdf, adapter.source_id, "parcel")

        if adapter.post_map is not None:
            gdf = adapter.post_map(gdf)

        for s in gdf["state_fips"].dropna().unique():
            if s:
                states_covered.add(str(s))

        part_path = parcels_dir / f"{safe_label}.parquet"
        write_geoparquet(gdf, part_path)
        canon_bytes += part_path.stat().st_size
        canon_row_total += len(gdf)
        output_files.append(part_path)
        qr_sample_parcels = gdf
        del gdf

    if n_layers_seen == 0:
        raise FileNotFoundError(f"{adapter.source_id}: no parcel layers under {raw_dir}")
    if n_layers_mapped == 0:
        # Loud failure beats the old silent "fall back to all layers", which
        # concatenated non-parcel layers into millions of garbage rows.
        raise RuntimeError(
            f"{adapter.source_id}: read {n_layers_seen} layer(s) but none carried an "
            f"owner column {owner_cols!r} — check the adapter's field_map."
        )

    log.info(
        "%s: %d/%d layers mapped → %d raw rows → %d canonical rows (%d dropped)",
        adapter.source_id,
        n_layers_mapped,
        n_layers_seen,
        raw_row_total,
        canon_row_total,
        dropped_total,
    )
    if dropped_total:
        log.warning("%s: dropped %d rows with null/invalid geometry", adapter.source_id, dropped_total)

    qr = quality_report(
        adapter.source_id,
        {"raw": qr_sample_raw, "parcels": qr_sample_parcels},
        warnings=(
            [f"dropped {dropped_total} rows with invalid geometry"] if dropped_total else None
        ),
    )
    # The QR tables were profiled from one representative layer (the full
    # set is too large to hold in memory) — correct the row counts to totals.
    for tbl, total in (("raw", raw_row_total), ("parcels", canon_row_total)):
        if tbl in qr.tables:
            qr.tables[tbl].rows = total
            qr.tables[tbl].note = (
                f"column stats sampled from 1 of {n_layers_mapped} layers; "
                "rows is the true total across all layers"
            )
    qr.extras["states_covered"] = sorted(states_covered)
    qr_path = write_quality_report(out_dir, qr)

    return NormalizeResult(
        raw_rows=raw_row_total,
        canonical_rows=canon_row_total,
        bytes=raw_bytes + canon_bytes,
        output_files=output_files + sorted(raw_dir_out.glob("*.parquet")) + [qr_path],
        canonical_types_written=["parcel"],
        quality_report=qr,
    )


# ── Registrations ────────────────────────────────────────────────────────


def _register(adapter: ParcelAdapter) -> ParcelNormalizer:
    return register_normalizer_instance(ParcelNormalizer(adapter))


# Imports kept at the bottom so the dataclass + driver are defined
# before the adapters try to reference ``ParcelAdapter``.
from .state_parcel_adapters.ar import AR_PARCELS_ADAPTER  # noqa: E402
from .state_parcel_adapters.fdor_nal import FDOR_NAL_ADAPTER  # noqa: E402
from .state_parcel_adapters.fl_fgdl import FL_FGDL_PARCELS_ADAPTER  # noqa: E402
from .state_parcel_adapters.mn import MN_PARCELS_ADAPTER  # noqa: E402
from .state_parcel_adapters.mt import MT_CADASTRAL_PARCELS_ADAPTER  # noqa: E402
from .state_parcel_adapters.nc import NC_ONEMAP_PARCELS_ADAPTER  # noqa: E402

_register(AR_PARCELS_ADAPTER)
_register(NC_ONEMAP_PARCELS_ADAPTER)
_register(MT_CADASTRAL_PARCELS_ADAPTER)
_register(FL_FGDL_PARCELS_ADAPTER)
_register(FDOR_NAL_ADAPTER)
_register(MN_PARCELS_ADAPTER)
