"""Florida — FDOR per-county PAR shapefile (taxable parcels w/ owners).

FDOR per-county PAR shapefile = PIN geometry + NAL tax-roll attributes
joined on PARCELNO. Verified against the 2025 PAR .dbf schema
(``alachua_2025Ppar``). Shapefile column names are capped at 10 chars,
so ``STATE_PARCEL_ID`` → ``STATE_PAR_`` etc.
"""

from __future__ import annotations

from .._adapter import ParcelAdapter

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
)
