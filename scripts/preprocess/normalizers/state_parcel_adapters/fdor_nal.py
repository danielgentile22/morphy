"""Florida — FDOR per-county PAR shapefile (taxable parcels w/ owners).

FDOR per-county PAR shapefile = PIN geometry + NAL tax-roll attributes
joined on PARCELNO. Verified against the 2025 PAR .dbf schema
(``alachua_2025Ppar``). Shapefile column names are capped at 10 chars,
so ``STATE_PARCEL_ID`` → ``STATE_PAR_`` etc.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from ..fdor_use_codes import land_use_desc
from ..pandas_coerce import safe_str
from ..state_parcels import ParcelAdapter

SQFT_PER_ACRE = 43_560.0


def _decode_land_use(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """E4: decode the FL DOR use code into the land-use description.

    ``land_use_code`` and ``land_use_desc`` both map from the bare ``DOR_UC``
    numeric code; this replaces the description with the documented text where
    the code is known (000–099), leaving the bare code for local codes ≥ 100 so
    nothing is mislabeled. The code column is untouched."""
    gdf = gdf.copy()
    gdf["land_use_desc"] = [land_use_desc(c) or safe_str(c) for c in gdf["land_use_code"]]
    return gdf


def _derive_acreage(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """M-m (#212): NAL ships land area as ``LND_SQFOOT`` (square feet), not
    acres — the field_map routes it into ``acreage`` and this converts
    (÷ 43,560). Nonpositive / missing square footage → null: FDOR uses 0 for
    "not recorded", which must not surface as a genuine 0-acre parcel."""
    gdf = gdf.copy()
    sqft = pd.to_numeric(gdf["acreage"], errors="coerce")
    gdf["acreage"] = (sqft / SQFT_PER_ACRE).where(sqft > 0)
    return gdf


def _fl_post_map(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return _derive_acreage(_decode_land_use(gdf))


FDOR_NAL_ADAPTER = ParcelAdapter(
    source_id="fdor_nal",
    state_fips="12",
    field_map={
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
        # NAL has no physical-state column (FL parcels are all FL); PHY_ZIPCD
        # carries the situs zip (E9).
        "situs_zip": ["PHY_ZIPCD"],
        # NAL ships LND_SQFOOT (square feet), not acres — routed here and
        # converted to acres by the _derive_acreage post_map (M-m / #212;
        # same pattern as MT's CityStateZ split).
        "acreage": ["LND_SQFOOT"],
        "land_value": ["LND_VAL"],
        # NAL has no direct improvement value (JV = land + improvements);
        # left null rather than compute, to keep the field map declarative.
        "improvement_value": [],
        "assessed_value": ["JV"],  # JV = just value (FL's market value)
        # M-k (#213): AV_NSD = assessed value, non-school-district — FL's
        # statutory assessed figure, distinct from JV (market) by exemptions.
        "statutory_assessed_value": ["AV_NSD"],
        "land_use_code": ["DOR_UC"],
        "land_use_desc": ["DOR_UC"],
        "year_built": ["ACT_YR_BLT"],
        # CENSUS_BK is a 12-digit census-block GEOID; canon_county_fips
        # slices positions 0-4 for the county FIPS.
        "county_fips": ["CENSUS_BK"],
    },
    post_map=_fl_post_map,
)
