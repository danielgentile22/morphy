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
from ..io import dual_write_spatial, write_raw_parquet
from ._helpers import (
    canon_county_fips,
    combine_address,
    safe_str,
    state_fips_from_county_fips,
    to_float,
    to_int,
)

log = logging.getLogger("preprocess.state_parcels")


# Per-state column maps. Keys are canonical-schema field names; values are
# lists of possible source column names (first match wins).
PARCEL_FIELD_MAPS: dict[str, dict[str, list[str]]] = {
    "nc_onemap_parcels": {
        "parcel_id": ["PARNO"],
        "parcel_id_full": ["NPARNO"],
        "owner_name": ["OWNNAME"],
        "owner_name_2": ["OWNNAME2"],
        "mailing_addr": ["MAILADD"],
        "mailing_city": ["MCITY"],
        "mailing_state": ["MSTATE"],
        "mailing_zip": ["MZIP"],
        "situs_addr": ["SITEADD"],
        "situs_city": ["SCITY"],
        "acreage": ["GISACRES"],
        "land_value": ["LANDVAL"],
        "improvement_value": ["IMPROVVAL"],
        "assessed_value": ["PARVAL"],
        "land_use_code": ["PARUSECODE"],
        "land_use_desc": ["PARUSEDESC"],
        "year_built": ["STRUCTYEAR"],
        "county_fips": ["STCNTYFIPS"],
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
        "parcel_id": ["PARCELID", "GEOCODE"],
        "parcel_id_full": ["GEOCODE"],
        "owner_name": ["OWNERNAME"],
        "mailing_addr": ["MAILADDRESS"],
        "mailing_city": ["CITYSTATEZIP"],
        "acreage": ["TotalAcres", "TOTALAcres"],
        "assessed_value": ["TaxValue", "AssessedValue"],
        "land_use_code": ["PropertyType"],
        "land_use_desc": ["PropertyType"],
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


# State FIPS hint per source_id — used when the source's county_fips field
# doesn't include the state prefix.
SOURCE_STATE_FIPS: dict[str, str] = {
    "nc_onemap_parcels": "37",
    "fl_fgdl_parcels": "12",
    "mn_parcels": "27",
    "mt_cadastral_parcels": "30",
    "in_parcels": "18",
    "ar_parcels": "05",
    "ut_parcels": "49",
}


def _pick_first(row: pd.Series, candidates: list[str]) -> object | None:
    for c in candidates:
        if c in row.index:
            v = row[c]
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                return v
    return None


def _read_multi_layer(path: Path) -> list[gpd.GeoDataFrame]:
    """Read every layer from a .gpkg / .gdb. pyogrio.list_layers returns
    a numpy.ndarray of shape (n_layers, 2) with [name, geometry_type] per
    row — extract just the name."""
    out: list[gpd.GeoDataFrame] = []
    try:
        import pyogrio

        layers = pyogrio.list_layers(path)
    except Exception as e:
        log.warning("  failed to list layers in %s: %s", path, e)
        return out
    # Normalize to list of names.
    names: list[str] = []
    try:
        for li in layers:
            if hasattr(li, "__len__") and len(li) > 0 and not isinstance(li, str):
                names.append(str(li[0]))
            else:
                names.append(str(li))
    except Exception:
        # ndarray fallback
        try:
            arr = layers
            for i in range(arr.shape[0]):
                names.append(str(arr[i, 0]))
        except Exception as e:
            log.warning("  couldn't parse layers from %s: %s", path, e)
            return out
    for lname in names:
        try:
            g = gpd.read_file(path, layer=lname)
            log.info("  read %s::%s: %d rows", path.name, lname, len(g))
            out.append(g)
        except Exception as e:
            log.warning("  failed to read %s::%s: %s", path.name, lname, e)
    return out


def _read_all_layers(raw_dir: Path) -> list[gpd.GeoDataFrame]:
    """Find every parcel layer under raw_dir and read it.

    Looks for .shp (each), .gdb folders (each layer), .gpkg files (each layer),
    .geojson files. Returns the list of (CRS-normalised) GeoDataFrames.
    """
    gdfs: list[gpd.GeoDataFrame] = []

    # Shapefiles
    for shp in sorted(raw_dir.rglob("*.shp")):
        try:
            g = gpd.read_file(shp)
            log.info("  read shapefile %s: %d rows", shp.relative_to(raw_dir), len(g))
            gdfs.append(g)
        except Exception as e:
            log.warning("  failed to read %s: %s", shp, e)

    # GeoPackages (each layer)
    for gpkg in sorted(raw_dir.rglob("*.gpkg")):
        for g in _read_multi_layer(gpkg):
            gdfs.append(g)

    # File Geodatabases (folders ending in .gdb)
    for gdb in sorted(p for p in raw_dir.rglob("*.gdb") if p.is_dir()):
        for g in _read_multi_layer(gdb):
            gdfs.append(g)

    # GeoJSON
    for gj in sorted(raw_dir.rglob("*.geojson")):
        try:
            g = gpd.read_file(gj)
            log.info("  read geojson %s: %d rows", gj.name, len(g))
            gdfs.append(g)
        except Exception as e:
            log.warning("  failed to read %s: %s", gj, e)

    # Normalize CRS to EPSG:4326
    out: list[gpd.GeoDataFrame] = []
    for g in gdfs:
        if g.crs is None:
            log.warning("  layer has no CRS — assuming EPSG:4326")
            g = g.set_crs("EPSG:4326")
        elif g.crs.to_epsg() != 4326:
            try:
                g = g.to_crs("EPSG:4326")
            except Exception as e:
                log.warning("  reproject failed (%s); skipping layer", e)
                continue
        out.append(g)
    return out


def _normalize_state_parcels(
    raw_dir: Path,
    out_dir: Path,
    source_id: str,
) -> NormalizeResult:
    field_map = PARCEL_FIELD_MAPS.get(source_id)
    if field_map is None:
        raise RuntimeError(f"no parcel field map for source_id {source_id!r}")
    expected_state_fips = SOURCE_STATE_FIPS.get(source_id)

    layers = _read_all_layers(raw_dir)
    if not layers:
        raise FileNotFoundError(f"{source_id}: no parcel layers under {raw_dir}")

    # Concatenate all layers — only the most parcel-like ones (have at least
    # one mapped column present).
    mapped = []
    for g in layers:
        if any(
            any(c in g.columns for c in cols)
            for canonical, cols in field_map.items()
            if canonical == "owner_name"
        ):
            mapped.append(g)
    if not mapped:
        # Fall back to all layers — better some data than none.
        mapped = layers
    combined = pd.concat(mapped, ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs="EPSG:4326")
    log.info("%s: combined %d layers → %d total rows", source_id, len(mapped), len(combined))

    raw_bytes = write_raw_parquet(combined, out_dir, name="raw.parquet")

    # Map to canonical schema
    rows = []
    for _, r in combined.iterrows():
        owner_name = safe_str(_pick_first(r, field_map.get("owner_name", [])))
        owner_name_2 = safe_str(_pick_first(r, field_map.get("owner_name_2", [])))
        mailing_addr = safe_str(_pick_first(r, field_map.get("mailing_addr", [])))
        mailing_city = safe_str(_pick_first(r, field_map.get("mailing_city", [])))
        mailing_state = safe_str(_pick_first(r, field_map.get("mailing_state", [])))
        mailing_zip = safe_str(_pick_first(r, field_map.get("mailing_zip", [])))
        situs_addr = safe_str(_pick_first(r, field_map.get("situs_addr", [])))
        situs_city = safe_str(_pick_first(r, field_map.get("situs_city", [])))
        county_fips_raw = _pick_first(r, field_map.get("county_fips", []))
        county_fips = canon_county_fips(county_fips_raw, state_fips=expected_state_fips)
        state_fips = state_fips_from_county_fips(county_fips) or expected_state_fips

        rows.append(
            {
                "parcel_id": safe_str(_pick_first(r, field_map.get("parcel_id", []))),
                "parcel_id_full": safe_str(_pick_first(r, field_map.get("parcel_id_full", []))),
                "owner_name": owner_name,
                "owner_name_2": owner_name_2,
                "owner_kind": infer_owner_kind(owner_name),
                "owner_name_norm": normalize_owner_name(owner_name),
                "mailing_addr": combine_address(
                    mailing_addr, mailing_city, mailing_state, mailing_zip
                ),
                "mailing_addr_norm": normalize_address(
                    combine_address(mailing_addr, mailing_city, mailing_state, mailing_zip)
                ),
                "mailing_city": mailing_city,
                "mailing_state": mailing_state,
                "mailing_zip": mailing_zip,
                "situs_addr": situs_addr,
                "situs_city": situs_city,
                "situs_state": None,
                "situs_zip": None,
                "acreage": to_float(_pick_first(r, field_map.get("acreage", []))),
                "land_value": to_float(_pick_first(r, field_map.get("land_value", []))),
                "improvement_value": to_float(
                    _pick_first(r, field_map.get("improvement_value", []))
                ),
                "assessed_value": to_float(_pick_first(r, field_map.get("assessed_value", []))),
                "land_use_code": safe_str(_pick_first(r, field_map.get("land_use_code", []))),
                "land_use_desc": safe_str(_pick_first(r, field_map.get("land_use_desc", []))),
                "year_built": to_int(_pick_first(r, field_map.get("year_built", []))),
                "county_fips": county_fips,
                "state_fips": state_fips,
                "extras": {},
                # Reverse-summary columns initialised; the Composer's
                # ParcelHostsInfraJoin will populate them.
                "has_tower": False,
                "tower_count": 0,
                "has_solar": False,
                "solar_count": 0,
                "has_billboard": False,
                "billboard_count": 0,
                "infrastructure_summary": [],
                "in_oz": False,
                "in_qct": False,
                "distress_overlays": [],
                "distress_tier": "",
                "persistent_poverty": False,
                "interestingness_score": 0.0,
                "interestingness_components": {},
                "owner_cluster_id": "",
                "owner_cluster_size": 0,
                "owner_cluster_value_total": 0.0,
                "_source_row_id": safe_str(_pick_first(r, field_map.get("parcel_id_full", []))),
                "geometry": r.geometry,
            }
        )
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    # Filter out null / invalid geometries — keep them in raw.parquet but
    # canonical needs valid polygons for joins.
    n_before = len(gdf)
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid].copy()
    dropped = n_before - len(gdf)
    if dropped:
        log.warning("%s: dropped %d rows with null/invalid geometry", source_id, dropped)

    gdf = add_polygon_derivatives(gdf)
    gdf = add_system_columns(gdf, source_id, "parcel")

    # write_simplified_geojson=True — parcels are big, browser wants the simplified copy
    files, written = dual_write_spatial(gdf, out_dir, "parcels", write_simplified_geojson=True)
    total = raw_bytes + written
    states_covered = sorted(set(s for s in gdf["state_fips"].dropna().unique() if s))
    qr = quality_report(
        source_id,
        {"raw": combined, "parcels": gdf},
        warnings=[f"dropped {dropped} rows with invalid geometry"] if dropped else None,
    )
    qr_path = write_quality_report(out_dir, qr)
    res = NormalizeResult(
        raw_rows=len(combined),
        canonical_rows=len(gdf),
        bytes=total,
        output_files=files + [out_dir / "raw.parquet", qr_path],
        canonical_types_written=["parcel"],
        quality_report=qr,
    )
    # Stuff states_covered into the result via the quality_report.
    res.quality_report["states_covered"] = states_covered
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
MnParcelsNormalizer = _make_parcel_normalizer("mn_parcels")
MtCadastralParcelsNormalizer = _make_parcel_normalizer("mt_cadastral_parcels")
InParcelsNormalizer = _make_parcel_normalizer("in_parcels")
ArParcelsNormalizer = _make_parcel_normalizer("ar_parcels")
UtParcelsNormalizer = _make_parcel_normalizer("ut_parcels")
