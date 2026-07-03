"""Arkansas — DataScout OneMap statewide layer (2026 vintage)."""

from __future__ import annotations

from ..state_parcels import ParcelAdapter

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
        # AR's AdrLabel/AdrCity/AdrZip5 ARE the situs (physical) location — the
        # parcel ships no separate owner-mailing column (E3 relabels it). Map
        # AdrZip5 as the situs zip too (E9). No situs-state column in OneMap.
        "situs_zip": ["AdrZip5"],
        "acreage": ["TaxArea"],
        "land_value": ["LandValue"],
        "improvement_value": ["ImpValue"],
        "assessed_value": ["TotalValue", "AssessValu"],
        # M-k (#213): AR's statutory assessed value (20% of appraised), distinct
        # from TotalValue (market). Same raw column that backstops assessed_value.
        "statutory_assessed_value": ["AssessValu"],
        "land_use_code": ["ParcelType"],
        "land_use_desc": ["ParcelType"],
        "county_fips": ["CountyFips"],
    },
)
