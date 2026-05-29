"""Florida — FGDL DSL parcel composite (state-owned land).

NOTE: this is the "DSL parcel composite" — state-owned land parcels
(Division of State Land), NOT general taxable parcels with owners. For
the FDOR NAL (with private owners), see ``fdor_nal``.

Map maintained against ``dsl_parcel_composite_oct25.gdb`` columns.
COUNTY_NAME only — no FIPS — so the driver falls back to ``state_fips``
('12') for every row.
"""

from __future__ import annotations

from ..state_parcels import ParcelAdapter

FL_FGDL_PARCELS_ADAPTER = ParcelAdapter(
    source_id="fl_fgdl_parcels",
    state_fips="12",
    field_map={
        "parcel_id": ["BTLDS_PARCEL_KEY", "DSL_PARCEL_COMPOSITE_KEY"],
        "parcel_id_full": ["DSL_PARCEL_COMPOSITE_KEY", "BTLDS_PARCEL_KEY"],
        "owner_name": ["FACILITY_NAME"],  # not a true owner — state-land facility
        "mailing_addr": [],
        "situs_addr": [],
        "acreage": ["PLOT_ACREAGE_NBR"],
        "land_use_code": ["LAND_CATEGORY_NAME"],
        "land_use_desc": ["LAND_CATEGORY_NAME"],
        # canon_county_fips can't resolve COUNTY_NAME; the driver's
        # state_fips fallback handles it.
        "county_fips": [],
    },
)
