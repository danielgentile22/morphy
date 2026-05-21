"""State-level parcel normalizers.

Every state's parcel layer maps to the same canonical schema; only the
column names differ. We declare per-state field mappings in PARCEL_FIELD_MAPS
and share a common _normalize_parcels() implementation.

Supports both shapefile and File Geodatabase. Reads everything in
data/raw/<source_id>/current/ — including multiple .gdb chunks (e.g. MN
split into chunks by anumber). All chunks concat into one canonical layer.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

from ..base import (
    Normalizer,
    NormalizeResult,
    add_system_columns,
    quality_report,
    register_normalizer,
    write_quality_report,
)
from ..cluster import infer_owner_kind, normalize_address, normalize_owner_name
from ..geom import add_polygon_derivatives
from ..io import write_geoparquet, write_raw_parquet
from ._helpers import (
    canon_county_fips,
    safe_str,
    state_fips_from_county_fips,
)

log = logging.getLogger("preprocess.state_parcels")


# Per-state column maps. Keys are canonical-schema field names; values are
# lists of possible source column names (first match wins).
PARCEL_FIELD_MAPS: dict[str, dict[str, list[str]]] = {
    "nc_onemap_parcels": {
        # Two casings per field: uppercase is the legacy shapefile bulk
        # download; lowercase is the MapServer /query GeoJSON output that
        # the current auto-fetch produces (see nc_onemap_parcels.py).
        "parcel_id": ["PARNO", "parno"],
        "parcel_id_full": ["NPARNO", "nparno"],
        "owner_name": ["OWNNAME", "ownname"],
        "owner_name_2": ["OWNNAME2", "ownname2"],
        "mailing_addr": ["MAILADD", "mailadd"],
        "mailing_city": ["MCITY", "mcity"],
        "mailing_state": ["MSTATE", "mstate"],
        "mailing_zip": ["MZIP", "mzip"],
        "situs_addr": ["SITEADD", "siteadd"],
        "situs_city": ["SCITY", "scity"],
        "acreage": ["GISACRES", "gisacres"],
        "land_value": ["LANDVAL", "landval"],
        "improvement_value": ["IMPROVVAL", "improvval"],
        "assessed_value": ["PARVAL", "parval"],
        "land_use_code": ["PARUSECODE", "parusecode"],
        "land_use_desc": ["PARUSEDESC", "parusedesc"],
        "year_built": ["STRUCTYEAR", "structyear"],
        "county_fips": ["STCNTYFIPS", "stcntyfips"],
    },
    "fl_fgdl_parcels": {
        # NOTE: the user's installed FL data is the FGDL "DSL parcel
        # composite" — state-owned land parcels (Division of State Land),
        # NOT general taxable parcels with owners. For the FDOR NAL
        # (with private owners), the user needs PARCELS_<YEAR>.zip from
        # the FGDL portal instead.
        # Map maintained against dsl_parcel_composite_oct25.gdb columns.
        "parcel_id": ["BTLDS_PARCEL_KEY", "DSL_PARCEL_COMPOSITE_KEY"],
        "parcel_id_full": ["DSL_PARCEL_COMPOSITE_KEY", "BTLDS_PARCEL_KEY"],
        "owner_name": ["FACILITY_NAME"],  # not a true owner — state-land facility
        "mailing_addr": [],
        "situs_addr": [],
        "acreage": ["PLOT_ACREAGE_NBR"],
        "land_use_code": ["LAND_CATEGORY_NAME"],
        "land_use_desc": ["LAND_CATEGORY_NAME"],
        # COUNTY_NAME only — no FIPS. canon_county_fips can't resolve this.
        # state_fips will fall back to '12' from SOURCE_STATE_FIPS.
        "county_fips": [],
    },
    # When the user downloads PARCELS_<YEAR>.zip (taxable parcels w/ NAL),
    # the columns differ; the puller stores it under fl_fgdl_parcels too,
    # so we'd need to detect-and-route in the normalizer if both could be
    # present. For Phase 1 we assume one or the other.
    "mn_parcels": {
        "parcel_id": ["PIN", "PARCEL_ID", "PARCEL_PIN"],
        "parcel_id_full": ["PIN"],
        "owner_name": ["OWNER_NAME", "OWNER1"],
        "mailing_addr": ["MAIL_ADDR1", "OWNER_ADDR"],
        "mailing_city": ["MAIL_CITY"],
        "mailing_state": ["MAIL_STATE"],
        "mailing_zip": ["MAIL_ZIP"],
        "situs_addr": ["PROP_ADDR", "SITE_ADDR"],
        "acreage": ["ACRES", "GIS_ACRES"],
        "land_value": ["LAND_VAL"],
        "improvement_value": ["BLDG_VAL"],
        "assessed_value": ["EST_MKT_VAL", "TOT_VAL"],
        "land_use_code": ["USE1_DESC", "USECLASS1"],
        "land_use_desc": ["USE1_DESC"],
        "year_built": ["YEAR_BUILT"],
        "county_fips": ["COUNTY_CD", "COUNTY_FIPS"],
    },
    "mt_cadastral_parcels": {
        # Verified against the MT Cadastral OWNERPARCEL.shp .dbf schema.
        # Shapefile 10-char column truncation: OwnerAddress→OwnerAddre,
        # TotalLandValue→TotalLandV, OwnerZipCode→OwnerZipCo, etc.
        "parcel_id": ["PARCELID"],
        "parcel_id_full": ["PARCELID"],
        "owner_name": ["OwnerName"],
        "owner_name_2": ["DbaName"],
        "mailing_addr": ["OwnerAddre"],
        "mailing_city": ["OwnerCity"],
        "mailing_state": ["OwnerState"],
        "mailing_zip": ["OwnerZipCo"],
        "situs_addr": ["AddressLin"],
        "acreage": ["GISAcres"],
        "land_value": ["TotalLandV"],
        "improvement_value": ["TotalBuild"],
        "assessed_value": ["TotalValue"],
        "land_use_code": ["PropType"],
        "land_use_desc": ["PropType"],
        # CountyName is a name, not a FIPS — resolved via
        # COUNTY_NAME_RESOLVERS below.
        "county_fips": ["CountyName"],
    },
    "in_parcels": {
        # IGIO Parcel Boundaries (Current) — no owner_name in public release.
        # Mailing/situs fields exist but the user has to look up owners via
        # the county assessor portals (out of scope for v1).
        "parcel_id": ["parcel_id", "state_parcel_id", "local_id"],
        "parcel_id_full": ["state_parcel_id", "parcel_id"],
        "owner_name": [],  # not in public IGIO release
        "mailing_addr": ["dlgf_prop_address"],
        "mailing_city": ["dlgf_prop_address_city"],
        "mailing_state": ["dlgf_prop_address_state"],
        "mailing_zip": ["dlgf_prop_address_zip"],
        "situs_addr": ["prop_add"],
        "situs_city": ["prop_city"],
        "land_use_code": ["dlgf_prop_class_code"],
        "county_fips": ["county_fips"],
    },
    "ar_parcels": {
        # Verified against DataScout OneMap statewide layer (2026 vintage).
        "parcel_id": ["ParcelId", "CountyId", "ParcelID"],
        "parcel_id_full": ["CountyId", "ParcelId"],
        "owner_name": ["OwnerName"],
        "mailing_addr": ["AdrLabel"],
        "mailing_city": ["AdrCity"],
        "mailing_zip": ["AdrZip5"],
        "situs_addr": ["AdrLabel"],
        "situs_city": ["AdrCity"],
        "acreage": ["TaxArea"],
        "land_value": ["LandValue"],
        "improvement_value": ["ImpValue"],
        "assessed_value": ["TotalValue", "AssessValu"],
        "land_use_code": ["ParcelType"],
        "land_use_desc": ["ParcelType"],
        "county_fips": ["CountyFips"],
    },
    "fdor_nal": {
        # FDOR per-county PAR shapefile = PIN geometry + NAL tax-roll
        # attributes joined on PARCELNO. Verified against the 2025 PAR
        # .dbf schema (alachua_2025Ppar). Shapefile column names are
        # capped at 10 chars, so STATE_PARCEL_ID → STATE_PAR_ etc.
        "parcel_id": ["PARCEL_ID", "PARCELNO"],
        "parcel_id_full": ["STATE_PAR_", "PARCEL_ID"],
        "owner_name": ["OWN_NAME"],
        "owner_name_2": [],
        "mailing_addr": ["OWN_ADDR1"],
        "mailing_city": ["OWN_CITY"],
        "mailing_state": ["OWN_STATE"],
        "mailing_zip": ["OWN_ZIPCD"],
        "situs_addr": ["PHY_ADDR1"],
        "situs_city": ["PHY_CITY"],
        # NAL ships LND_SQFOOT (square feet), not acres — left null
        # rather than mislabel sqft as acreage.
        "acreage": [],
        "land_value": ["LND_VAL"],
        # NAL has no direct improvement value (JV = land + improvements);
        # left null rather than compute, to keep the field map declarative.
        "improvement_value": [],
        "assessed_value": ["JV"],  # JV = just value (FL's market value)
        "land_use_code": ["DOR_UC"],
        "land_use_desc": ["DOR_UC"],
        "year_built": ["ACT_YR_BLT"],
        # CENSUS_BK is a 12-digit census-block GEOID; canon_county_fips
        # slices positions 0-4 for the county FIPS.
        "county_fips": ["CENSUS_BK"],
    },
    "ut_parcels": {
        "parcel_id": ["PARCEL_ID"],
        "parcel_id_full": ["PARCEL_ID"],
        "owner_name": ["OWNER_NAME"],
        "mailing_addr": ["OWNER_ADDR"],
        "mailing_city": ["OWNER_CITY"],
        "mailing_state": ["OWNER_STAT"],
        "mailing_zip": ["OWNER_ZIP"],
        "situs_addr": ["PROP_ADDR"],
        "acreage": ["TAX_AREA", "ACRES"],
        "assessed_value": ["TOTAL_MKT"],
        "land_use_code": ["LAND_USE"],
        "county_fips": ["COUNTY"],
    },
}


# Montana county name → 5-digit FIPS. The MT Cadastral OWNERPARCEL layer
# identifies counties only by name (CountyName); there is no FIPS column.
# MT FIPS are alphabetical, odd codes 30001-30111.
MT_COUNTY_NAME_TO_FIPS: dict[str, str] = {
    "BEAVERHEAD": "30001", "BIG HORN": "30003", "BLAINE": "30005",
    "BROADWATER": "30007", "CARBON": "30009", "CARTER": "30011",
    "CASCADE": "30013", "CHOUTEAU": "30015", "CUSTER": "30017",
    "DANIELS": "30019", "DAWSON": "30021", "DEER LODGE": "30023",
    "FALLON": "30025", "FERGUS": "30027", "FLATHEAD": "30029",
    "GALLATIN": "30031", "GARFIELD": "30033", "GLACIER": "30035",
    "GOLDEN VALLEY": "30037", "GRANITE": "30039", "HILL": "30041",
    "JEFFERSON": "30043", "JUDITH BASIN": "30045", "LAKE": "30047",
    "LEWIS AND CLARK": "30049", "LIBERTY": "30051", "LINCOLN": "30053",
    "MCCONE": "30055", "MADISON": "30057", "MEAGHER": "30059",
    "MINERAL": "30061", "MISSOULA": "30063", "MUSSELSHELL": "30065",
    "PARK": "30067", "PETROLEUM": "30069", "PHILLIPS": "30071",
    "PONDERA": "30073", "POWDER RIVER": "30075", "POWELL": "30077",
    "PRAIRIE": "30079", "RAVALLI": "30081", "RICHLAND": "30083",
    "ROOSEVELT": "30085", "ROSEBUD": "30087", "SANDERS": "30089",
    "SHERIDAN": "30091", "SILVER BOW": "30093", "STILLWATER": "30095",
    "SWEET GRASS": "30097", "TETON": "30099", "TOOLE": "30101",
    "TREASURE": "30103", "VALLEY": "30105", "WHEATLAND": "30107",
    "WIBAUX": "30109", "YELLOWSTONE": "30111",
}

# Sources whose county field carries a county *name* rather than a FIPS
# code. The vectorized normalizer resolves these via name lookup instead
# of canon_county_fips. Key = source_id, value = {UPPERCASE name: FIPS}.
COUNTY_NAME_RESOLVERS: dict[str, dict[str, str]] = {
    "mt_cadastral_parcels": MT_COUNTY_NAME_TO_FIPS,
}


# State FIPS hint per source_id — used when the source's county_fips field
# doesn't include the state prefix.
SOURCE_STATE_FIPS: dict[str, str] = {
    "nc_onemap_parcels": "37",
    "fl_fgdl_parcels": "12",
    "fdor_nal": "12",
    "mn_parcels": "27",
    "mt_cadastral_parcels": "30",
    "in_parcels": "18",
    "ar_parcels": "05",
    "ut_parcels": "49",
}


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

    Streaming — only one layer is held at a time. The old _read_all_layers
    materialised every layer before concatenating, which needs ~50 GB peak
    for FL's 67-county / ~28 GB FDOR set. This generator keeps peak memory
    bounded to a single county.
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


def _map_layer_to_canonical(
    g: gpd.GeoDataFrame,
    field_map: dict[str, list[str]],
    source_id: str,
    expected_state_fips: str | None,
) -> gpd.GeoDataFrame:
    """Map one raw parcel layer to the canonical narrow schema.

    Vectorized — every canonical column is a column-wise operation; the
    three regex-heavy scalar functions (infer_owner_kind,
    normalize_owner_name, normalize_address) run once per *distinct* value.
    Returns the narrow GeoDataFrame *before* the geometry-validity filter.
    """
    fm = field_map
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
    name_resolver = COUNTY_NAME_RESOLVERS.get(source_id)
    if name_resolver is not None:
        # Source identifies counties by name (e.g. MT Cadastral).
        county_fips = _map_unique(county_raw, lambda v: name_resolver.get(v.strip().upper()))
    else:
        county_fips = _map_unique(
            county_raw, lambda v: canon_county_fips(v, state_fips=expected_state_fips)
        )
    state_fips = _map_unique(
        county_fips, lambda v: state_fips_from_county_fips(v) or expected_state_fips
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


def _normalize_state_parcels(
    raw_dir: Path,
    out_dir: Path,
    source_id: str,
) -> NormalizeResult:
    """Streaming per-layer normalize.

    Each input layer (county shapefile, GeoJSON page, gdb layer) is read,
    mapped to the canonical schema, geometry-filtered, and written to its
    own ``parcels/<label>.parquet`` — a standard multi-file parquet
    dataset the Composer reads back. Peak memory stays bounded to a single
    layer, so FL's 67-county / ~10M-parcel set works on a 16 GB machine.
    """
    field_map = PARCEL_FIELD_MAPS.get(source_id)
    if field_map is None:
        raise RuntimeError(f"no parcel field map for source_id {source_id!r}")
    expected_state_fips = SOURCE_STATE_FIPS.get(source_id)
    owner_cols = field_map.get("owner_name", [])
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
            log.info("  %s: skip layer %s — no owner column (not a parcel layer)", source_id, label)
            continue
        n_layers_mapped += 1
        raw_row_total += len(g)
        safe_label = re.sub(r"[^A-Za-z0-9_.-]", "_", label)

        raw_bytes += write_raw_parquet(g, raw_dir_out, name=f"{safe_label}.parquet")
        if qr_sample_raw is None:
            qr_sample_raw = g

        gdf = _map_layer_to_canonical(g, field_map, source_id, expected_state_fips)
        del g  # free the wide raw frame before the next layer

        n_before = len(gdf)
        gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid].copy()
        dropped_total += n_before - len(gdf)

        gdf = add_polygon_derivatives(gdf)
        gdf = add_system_columns(gdf, source_id, "parcel")

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
        raise FileNotFoundError(f"{source_id}: no parcel layers under {raw_dir}")
    if n_layers_mapped == 0:
        # Loud failure beats the old silent "fall back to all layers", which
        # concatenated non-parcel layers into millions of garbage rows.
        raise RuntimeError(
            f"{source_id}: read {n_layers_seen} layer(s) but none carried an "
            f"owner column {owner_cols!r} — check PARCEL_FIELD_MAPS."
        )

    log.info(
        "%s: %d/%d layers mapped → %d raw rows → %d canonical rows (%d dropped)",
        source_id,
        n_layers_mapped,
        n_layers_seen,
        raw_row_total,
        canon_row_total,
        dropped_total,
    )
    if dropped_total:
        log.warning("%s: dropped %d rows with null/invalid geometry", source_id, dropped_total)

    qr = quality_report(
        source_id,
        {"raw": qr_sample_raw, "parcels": qr_sample_parcels},
        warnings=(
            [f"dropped {dropped_total} rows with invalid geometry"] if dropped_total else None
        ),
    )
    # The QR tables were profiled from one representative layer (the full
    # set is too large to hold in memory) — correct the row counts to totals.
    for tbl, total in (("raw", raw_row_total), ("parcels", canon_row_total)):
        if tbl in qr.get("tables", {}):
            qr["tables"][tbl]["rows"] = total
            qr["tables"][tbl]["note"] = (
                f"column stats sampled from 1 of {n_layers_mapped} layers; "
                "rows is the true total across all layers"
            )
    qr_path = write_quality_report(out_dir, qr)

    res = NormalizeResult(
        raw_rows=raw_row_total,
        canonical_rows=canon_row_total,
        bytes=raw_bytes + canon_bytes,
        output_files=output_files + sorted(raw_dir_out.glob("*.parquet")) + [qr_path],
        canonical_types_written=["parcel"],
        quality_report=qr,
    )
    res.quality_report["states_covered"] = sorted(states_covered)
    return res


def _make_parcel_normalizer(source_id_value: str):
    """Build a concrete Normalizer subclass for one state parcel source.

    We define normalize() at class-creation time (not as a post-hoc
    attribute assignment) so the ABCMeta abstract-method check passes when
    @register_normalizer instantiates the class.
    """
    captured = source_id_value
    cls_name = f"_ParcelNormalizer_{captured}"
    body = {
        "source_id": captured,
        "canonical_types": ["parcel"],
        "normalize": lambda self, raw_dir, out_dir: _normalize_state_parcels(
            raw_dir,
            out_dir,
            captured,
        ),
    }
    cls = type(cls_name, (Normalizer,), body)
    return register_normalizer(cls)


# Register one Normalizer per state parcel source.
NcOnemapParcelsNormalizer = _make_parcel_normalizer("nc_onemap_parcels")
FlFgdlParcelsNormalizer = _make_parcel_normalizer("fl_fgdl_parcels")
FdorNalNormalizer = _make_parcel_normalizer("fdor_nal")
MnParcelsNormalizer = _make_parcel_normalizer("mn_parcels")
MtCadastralParcelsNormalizer = _make_parcel_normalizer("mt_cadastral_parcels")
InParcelsNormalizer = _make_parcel_normalizer("in_parcels")
ArParcelsNormalizer = _make_parcel_normalizer("ar_parcels")
UtParcelsNormalizer = _make_parcel_normalizer("ut_parcels")
