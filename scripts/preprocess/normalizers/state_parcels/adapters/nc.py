"""North Carolina — NC OneMap statewide parcels.

Two casings per field: uppercase is the legacy shapefile bulk download;
lowercase is the MapServer /query GeoJSON output that the current
auto-fetch produces (see ``scripts/fetch/sources/nc_onemap_parcels.py``).
"""

from __future__ import annotations

from .._adapter import ParcelAdapter

NC_ONEMAP_PARCELS_ADAPTER = ParcelAdapter(
    source_id="nc_onemap_parcels",
    state_fips="37",
    field_map={
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
)
