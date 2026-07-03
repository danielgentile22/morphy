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
class AttributeJoin:
    """A sidecar non-spatial table merged onto each spatial layer.

    Some statewide feeds split the parcel record across two objects in
    one container: a thin geometry feature class plus a standalone
    attribute table holding the owner/value/land-use detail, related by a
    shared key (WV's ``MasterSurfWV`` polygons + ``ParcelSummary`` table,
    joined on ``CleanParcelID``). The driver left-merges the named table's
    ``columns`` onto every spatial layer before canonical mapping, so the
    existing column-driven ``field_map`` can reach the joined attributes.

    Attributes:
        layer_name: Exact layer name of the attribute table in the .gdb /
            .gpkg (e.g. ``"ParcelSummary"``).
        left_key / right_key: Join columns on the spatial layer and on the
            attribute table (usually identical).
        columns: Columns to pull from the attribute table. Keep this to the
            fields the ``field_map`` actually needs — the table is read in
            full, so a narrow projection keeps peak memory bounded. The
            join key is always included automatically. **These names must
            not collide with the spatial layer's own columns** (other than
            the key) — collisions would be silently suffixed by the merge.
    """

    layer_name: str
    left_key: str
    right_key: str
    columns: list[str]


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
        attribute_join: Optional sidecar attribute table to left-merge onto
            each spatial layer before mapping (see ``AttributeJoin``). When
            None (the default) the driver reads only the spatial layers, as
            every other source does.
        mailing_addr_is_full: When True the ``mailing_addr`` field_map
            candidate is already a complete single-line mailing address
            (street + city + state + zip), so the driver does **not**
            re-append the structured ``mailing_city/state/zip`` parts to the
            composite (which would duplicate them). The structured columns
            still populate from their own candidates. Default False — most
            sources supply a street-only line that needs the city/state/zip
            appended.
    """

    source_id: str
    state_fips: str
    field_map: dict[str, list[str]]
    county_resolver: CountyResolver | None = None
    post_map: PostMap | None = None
    attribute_join: AttributeJoin | None = None
    mailing_addr_is_full: bool = False


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


def _looks_like_lonlat(g: gpd.GeoDataFrame) -> bool:
    """True when a layer's coordinate bounds fall inside the valid lon/lat
    envelope. The only case where assuming an *unlabeled* CRS is EPSG:4326 is
    safe — otherwise ``set_crs`` would silently mislabel a projected layer
    (e.g. State Plane feet, where coordinates run into the millions) as WGS84
    and corrupt every downstream spatial join."""
    try:
        minx, miny, maxx, maxy = g.total_bounds
    except Exception:
        return False
    if any(pd.isna(v) for v in (minx, miny, maxx, maxy)):
        return False
    return -180.0 <= minx and maxx <= 180.0 and -90.0 <= miny and maxy <= 90.0


def _to_4326(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame | None:
    """Reproject one layer to EPSG:4326. Returns None if reprojection fails
    or an unlabeled layer cannot be safely assumed to already be lon/lat."""
    if g.crs is None:
        # No CRS — only assume 4326 when the coordinates actually look like
        # lon/lat. Mislabeling projected data as WGS84 corrupts joins silently
        # and irreversibly, so a layer that fails the check is skipped (loud
        # log) rather than mislabeled. The CRS must be declared upstream.
        if _looks_like_lonlat(g):
            log.warning("  layer has no CRS — coordinates look like lon/lat, assuming EPSG:4326")
            return g.set_crs("EPSG:4326")
        log.error(
            "  layer has no CRS and coordinates are outside the lon/lat range — "
            "skipping (cannot assume EPSG:4326 without mislabeling projected data)"
        )
        return None
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
    # pyogrio.list_layers rows are [name, geometry_type]; geometry_type is
    # None for non-spatial tables (e.g. WV's ParcelSummary attribute table).
    # Skip those here — they're handled as AttributeJoin sidecars, never
    # mapped as parcel layers, and reading them in full just to discard
    # them wastes time + memory.
    names: list[str] = []
    try:
        for li in layers:
            if hasattr(li, "__len__") and len(li) > 0 and not isinstance(li, str):
                geom_type = li[1] if len(li) > 1 else None
                if geom_type is None or str(geom_type) in ("", "None"):
                    log.info("  skip non-spatial layer %s::%s", path.name, li[0])
                    continue
                names.append(str(li[0]))
            else:
                names.append(str(li))
    except Exception:
        try:
            for i in range(layers.shape[0]):
                geom_type = layers[i, 1] if layers.shape[1] > 1 else None
                if geom_type is None or str(geom_type) in ("", "None"):
                    continue
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
    if adapter.mailing_addr_is_full:
        # The mailing_addr candidate is already a complete single-line
        # address (street + city + state + zip) — appending the structured
        # parts again would duplicate them. The structured mailing_city /
        # state / zip columns below still populate from their own candidates.
        mailing_addr = _str_series(g, fm.get("mailing_addr", []))
    else:
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
    # E9: populate situs state/zip from the raw where the adapter's field_map
    # carries them (was hard-coded None for every state, cutting the situs
    # address off at the city). States whose raw has no such column stay blank;
    # MT parses its combined CityStateZ in a post_map (E12).
    out["situs_state"] = _str_series(g, fm.get("situs_state", []))
    out["situs_zip"] = _str_series(g, fm.get("situs_zip", []))
    out["acreage"] = _num_series(g, fm.get("acreage", []))
    out["land_value"] = _num_series(g, fm.get("land_value", []))
    out["improvement_value"] = _num_series(g, fm.get("improvement_value", []))
    out["assessed_value"] = _num_series(g, fm.get("assessed_value", []))
    # M-k (#213, ADR-070): the true statutory assessed figure, distinct from the
    # market/appraised value above. Direct raw column where the source ships one
    # (FL AV_NSD, AR AssessValu); WV computes 60%-of-appraised in its post_map;
    # MT has no such field → the empty field_map leaves it null.
    out["statutory_assessed_value"] = _num_series(g, fm.get("statutory_assessed_value", []))
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
    # Billboard columns dropped (E14): every billboard source is deferred, so
    # has_billboard/billboard_count were false/0 on 100% of parcels.
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
    # Geometry-validity status column. Full-fidelity preservation (CLAUDE §8 /
    # ARCHITECTURE §3.3) means we never drop rows at normalize time — invalid /
    # null geometry is flagged here, and compose's spatial joins filter on it.
    out["geometry_valid"] = (g.geometry.notna() & g.geometry.is_valid).values

    return gpd.GeoDataFrame(out, geometry="geometry", crs="EPSG:4326")


# ── Driver entry point ───────────────────────────────────────────────────


def _read_attribute_table(raw_dir: Path, join: AttributeJoin) -> pd.DataFrame | None:
    """Read an ``AttributeJoin`` sidecar table (its key + requested columns)
    from the first .gdb/.gpkg under ``raw_dir`` that contains it, deduped to
    one row per join key. Returns None if the table can't be found/read."""
    try:
        import pyogrio
    except Exception as e:  # pragma: no cover - pyogrio is a hard dep in practice
        log.warning("  attribute join needs pyogrio, unavailable: %s", e)
        return None
    want = list(dict.fromkeys([join.right_key, *join.columns]))
    containers = [p for p in sorted(raw_dir.rglob("*.gdb")) if p.is_dir()]
    containers += sorted(raw_dir.rglob("*.gpkg"))
    for container in containers:
        try:
            names = {str(li[0]) for li in pyogrio.list_layers(container)}
        except Exception:
            continue
        if join.layer_name not in names:
            continue
        try:
            df = pyogrio.read_dataframe(
                container, layer=join.layer_name, read_geometry=False, columns=want
            )
        except Exception as e:
            log.warning(
                "  failed to read attribute table %s::%s: %s",
                container.name,
                join.layer_name,
                e,
            )
            return None
        before = len(df)
        # One attribute row per parcel; keep the first when a key repeats
        # (e.g. WV ParcelSummary has a handful of multi-card parcels).
        df = df.drop_duplicates(subset=join.right_key, keep="first")
        log.info(
            "  attribute join: %s::%s — %d rows → %d unique %s",
            container.name,
            join.layer_name,
            before,
            len(df),
            join.right_key,
        )
        return df
    log.warning("  attribute-join table %r not found under %s", join.layer_name, raw_dir)
    return None


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

    # Optional sidecar attribute table (e.g. WV ParcelSummary) read once and
    # left-merged onto each spatial layer below, so the field_map can reach
    # the joined owner/value/land-use columns.
    attr_df = (
        _read_attribute_table(raw_dir, adapter.attribute_join)
        if adapter.attribute_join is not None
        else None
    )

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
    invalid_total = 0
    n_layers_seen = 0
    n_layers_mapped = 0
    states_covered: set[str] = set()
    output_files: list[Path] = []
    qr_sample_raw: gpd.GeoDataFrame | None = None
    qr_sample_parcels: gpd.GeoDataFrame | None = None

    for label, g in _iter_raw_layers(raw_dir):
        n_layers_seen += 1
        # Merge the attribute sidecar before the owner-column check so the
        # check (and the canonical mapping) can see the joined columns —
        # WV's owner/value detail lives only in the joined ParcelSummary.
        if attr_df is not None and adapter.attribute_join.left_key in g.columns:
            g = g.merge(
                attr_df,
                left_on=adapter.attribute_join.left_key,
                right_on=adapter.attribute_join.right_key,
                how="left",
                suffixes=("", "_attr"),
            )
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

        # Keep every row (full-fidelity raw preservation, CLAUDE §8 /
        # ARCHITECTURE §3.3). map_layer_to_canonical flags invalid/null
        # geometry via geometry_valid; compose's spatial joins exclude those
        # rows from sjoins rather than this normalizer dropping them.
        invalid_total += int((~gdf["geometry_valid"]).sum())

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
        "%s: %d/%d layers mapped → %d raw rows → %d canonical rows (%d invalid-geom, kept + flagged)",
        adapter.source_id,
        n_layers_mapped,
        n_layers_seen,
        raw_row_total,
        canon_row_total,
        invalid_total,
    )
    if invalid_total:
        log.warning(
            "%s: %d rows have null/invalid geometry — kept with geometry_valid=False",
            adapter.source_id,
            invalid_total,
        )

    qr = quality_report(
        adapter.source_id,
        {"raw": qr_sample_raw, "parcels": qr_sample_parcels},
        warnings=(
            [f"{invalid_total} rows have invalid/null geometry (kept, geometry_valid=False)"]
            if invalid_total
            else None
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
from .state_parcel_adapters.mn import MN_PARCELS_ADAPTER  # noqa: E402, F401
from .state_parcel_adapters.mt import MT_CADASTRAL_PARCELS_ADAPTER  # noqa: E402
from .state_parcel_adapters.nc import NC_ONEMAP_PARCELS_ADAPTER  # noqa: E402
from .state_parcel_adapters.wv import WV_PARCELS_ADAPTER  # noqa: E402

_register(AR_PARCELS_ADAPTER)
_register(NC_ONEMAP_PARCELS_ADAPTER)
_register(MT_CADASTRAL_PARCELS_ADAPTER)
_register(FL_FGDL_PARCELS_ADAPTER)
_register(FDOR_NAL_ADAPTER)
_register(WV_PARCELS_ADAPTER)

# Minnesota (fips 27) is DEFERRED — intentionally not registered into the
# active normalizer set. ADR-018 defers the MN pull pending MnGeo
# confirmation, and the source is marked "No License Provided" despite the
# "Plan Parcels Open" name — a commercial-use blocker (see memory
# `mn-parcels-license-commercial-blocker`). The adapter is imported above so
# it stays maintained; re-enable by uncommenting the line below once the
# licence terms and scope are confirmed.
# _register(MN_PARCELS_ADAPTER)
