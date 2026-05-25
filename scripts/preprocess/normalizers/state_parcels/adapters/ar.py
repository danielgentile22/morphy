"""Arkansas — DataScout OneMap statewide layer (2026 vintage)."""

from __future__ import annotations

from .._adapter import ParcelAdapter

AR_PARCELS_ADAPTER = ParcelAdapter(
    source_id="ar_parcels",
    state_fips="05",
    field_map={
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
)
