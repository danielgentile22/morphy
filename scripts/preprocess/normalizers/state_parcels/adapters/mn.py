"""Minnesota — Plan Parcels Open.

Multiple .gdb chunks (the source ships parcels split by anumber); all
layers concat into one canonical layer via the streaming driver.

Commercial-use caveat: the MN source is marked "No License Provided"
despite the "Plan Parcels Open" name — flag before any commercial use.
"""

from __future__ import annotations

from .._adapter import ParcelAdapter

MN_PARCELS_ADAPTER = ParcelAdapter(
    source_id="mn_parcels",
    state_fips="27",
    field_map={
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
)
