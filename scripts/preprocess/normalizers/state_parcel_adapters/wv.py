"""West Virginia — statewide tax-parcel layer (MapWV / WVGISTC, SB 588).

Verified against the downloaded ``WV_WVGISTC_Tax_2025.gdb`` (Tax Year 2025,
~1.39M parcels, all 55 counties). The feed splits the parcel record across
two objects in one geodatabase:

  * ``MasterSurfWV_2025`` — the polygon feature class (EPSG:26917), with a
    thin owner set (FullOwnerName/Address) and a 2-digit ``CountyID``.
  * ``ParcelSummary`` — a standalone, geometry-less table holding the full
    WV IAS assessment record (granular owner, mailing, land/improvement/
    total appraised value, land use), related on ``CleanParcelID``.

The full owner/value/land-use attributes therefore only exist once
``ParcelSummary`` is joined on — handled by ``AttributeJoin`` in the shared
driver. The parcel record names the SURFACE owner (split-estate is the norm
in rural WV; minerals are commonly severed) — that surface owner is exactly
our tower-lease target; do not conflate with mineral ownership.

County FIPS: WV's own ``CountyID`` / ``CountyCode`` is an alphabetical
01..55 sequence that does **not** equal the Census ANSI county FIPS — Census
collates "McDowell" (54047) *before* "Marion" (54049), whereas WV orders
Marion=24, McDowell=27. A bare prefix-concat ("01"→"54001") would silently
mis-assign half the counties, so we resolve via an explicit, verified table.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from ..state_parcels import AttributeJoin, ParcelAdapter

# WV county NAME → Census ANSI 5-digit FIPS (54001..54109, odd). Authoritative
# Census ordering: McDowell=54047 sorts before Marion=54049 (the one deviation
# from naive alphabetical). Verified: every CountyName in the 2025 layer
# resolves, all 55 unique.
WV_COUNTY_NAME_TO_FIPS: dict[str, str] = {
    "BARBOUR": "54001",
    "BERKELEY": "54003",
    "BOONE": "54005",
    "BRAXTON": "54007",
    "BROOKE": "54009",
    "CABELL": "54011",
    "CALHOUN": "54013",
    "CLAY": "54015",
    "DODDRIDGE": "54017",
    "FAYETTE": "54019",
    "GILMER": "54021",
    "GRANT": "54023",
    "GREENBRIER": "54025",
    "HAMPSHIRE": "54027",
    "HANCOCK": "54029",
    "HARDY": "54031",
    "HARRISON": "54033",
    "JACKSON": "54035",
    "JEFFERSON": "54037",
    "KANAWHA": "54039",
    "LEWIS": "54041",
    "LINCOLN": "54043",
    "LOGAN": "54045",
    "MCDOWELL": "54047",
    "MARION": "54049",
    "MARSHALL": "54051",
    "MASON": "54053",
    "MERCER": "54055",
    "MINERAL": "54057",
    "MINGO": "54059",
    "MONONGALIA": "54061",
    "MONROE": "54063",
    "MORGAN": "54065",
    "NICHOLAS": "54067",
    "OHIO": "54069",
    "PENDLETON": "54071",
    "PLEASANTS": "54073",
    "POCAHONTAS": "54075",
    "PRESTON": "54077",
    "PUTNAM": "54079",
    "RALEIGH": "54081",
    "RANDOLPH": "54083",
    "RITCHIE": "54085",
    "ROANE": "54087",
    "SUMMERS": "54089",
    "TAYLOR": "54091",
    "TUCKER": "54093",
    "TYLER": "54095",
    "UPSHUR": "54097",
    "WAYNE": "54099",
    "WEBSTER": "54101",
    "WETZEL": "54103",
    "WIRT": "54105",
    "WOOD": "54107",
    "WYOMING": "54109",
}

# WV internal 2-digit county code ("01".."55") → Census FIPS, derived from the
# layer's own CountyCode↔CountyName pairing against the table above. Lets us
# resolve county from the polygon's CountyID (present on every row, no join
# dependency). Note codes 24-27 = Marion/Marshall/Mason/McDowell map to
# 54049/54051/54053/54047 — McDowell (27) is out of numeric order vs Census.
WV_COUNTY_CODE_TO_FIPS: dict[str, str] = {
    "01": "54001",
    "02": "54003",
    "03": "54005",
    "04": "54007",
    "05": "54009",
    "06": "54011",
    "07": "54013",
    "08": "54015",
    "09": "54017",
    "10": "54019",
    "11": "54021",
    "12": "54023",
    "13": "54025",
    "14": "54027",
    "15": "54029",
    "16": "54031",
    "17": "54033",
    "18": "54035",
    "19": "54037",
    "20": "54039",
    "21": "54041",
    "22": "54043",
    "23": "54045",
    "24": "54049",
    "25": "54051",
    "26": "54053",
    "27": "54047",
    "28": "54055",
    "29": "54057",
    "30": "54059",
    "31": "54061",
    "32": "54063",
    "33": "54065",
    "34": "54067",
    "35": "54069",
    "36": "54071",
    "37": "54073",
    "38": "54075",
    "39": "54077",
    "40": "54079",
    "41": "54081",
    "42": "54083",
    "43": "54085",
    "44": "54087",
    "45": "54089",
    "46": "54091",
    "47": "54093",
    "48": "54095",
    "49": "54097",
    "50": "54099",
    "51": "54101",
    "52": "54103",
    "53": "54105",
    "54": "54107",
    "55": "54109",
}


def _resolve_wv_county(value: str) -> str | None:
    """Resolve WV's CountyID code ("01".."55") or a county name to Census FIPS."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return WV_COUNTY_CODE_TO_FIPS.get(f"{int(s):02d}")
    return WV_COUNTY_NAME_TO_FIPS.get(s.upper())


# WV statutory assessed value = 60% of appraised, by law (WV Const. Art. X §1b).
# It's not a stored column — the feed ships only TotalAppraisal (→ assessed_value,
# the market/appraised figure) — so we derive it here (M-k / #213 / ADR-070).
_WV_ASSESSED_RATIO = 0.60


def _wv_post_map(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    gdf["statutory_assessed_value"] = _WV_ASSESSED_RATIO * pd.to_numeric(
        gdf["assessed_value"], errors="coerce"
    )
    return gdf


WV_PARCELS_ADAPTER = ParcelAdapter(
    source_id="wv_parcels",  # MUST equal the fetch-side DataSource.id
    state_fips="54",
    # Column names verified against WV_WVGISTC_Tax_2025.gdb. Owner1/Owner2 +
    # value + land-use + structured mailing come from the joined ParcelSummary
    # table; FullOwnerName/Address and CountyID are on the polygon layer.
    field_map={
        "parcel_id": ["CleanParcelID"],
        "parcel_id_full": ["CleanParcelID"],
        "owner_name": ["Owner1", "FullOwnerName"],
        "owner_name_2": ["Owner2"],
        # FullOwnerAddress is a complete single-line mailing address
        # (street + city + state + zip) → mailing_addr_is_full=True below
        # so the structured parts aren't appended twice.
        "mailing_addr": ["FullOwnerAddress"],
        "mailing_city": ["OwnerCity"],
        "mailing_state": ["OwnerStateCode"],
        "mailing_zip": ["OwnerZipCode"],
        "situs_addr": ["FullPhysicalAddress"],
        "acreage": ["CalculatedAcres", "DeededAcres", "Acres_C"],
        "land_value": ["LandAppraisal"],
        "improvement_value": ["BuildingAppraisal"],
        # TotalAppraisal is the total APPRAISED value; WV statutory assessed
        # value is 60% of appraised and is not a stored column.
        "assessed_value": ["TotalAppraisal"],
        "land_use_code": ["LandUseCode", "PropertyClassCode"],
        "land_use_desc": ["LandUse", "PropertyClassDescription"],
        # YearBuilt rides the joined ParcelSummary (~54% populated); was
        # unmapped → 100% null in output (E11).
        "year_built": ["YearBuilt"],
        # CountyID (polygon, every row) preferred; CountyName/Code as fallback.
        "county_fips": ["CountyID", "CountyName", "CountyCode"],
    },
    county_resolver=_resolve_wv_county,
    post_map=_wv_post_map,
    mailing_addr_is_full=True,
    attribute_join=AttributeJoin(
        layer_name="ParcelSummary",
        left_key="CleanParcelID",
        right_key="CleanParcelID",
        # Pulled from ParcelSummary; none of these names collide with the
        # MasterSurfWV polygon columns (other than the join key).
        columns=[
            "Owner1",
            "Owner2",
            "OwnerCity",
            "OwnerStateCode",
            "OwnerZipCode",
            "LandAppraisal",
            "BuildingAppraisal",
            "TotalAppraisal",
            "LandUse",
            "LandUseCode",
            "PropertyClassCode",
            "PropertyClassDescription",
            "YearBuilt",
            "CalculatedAcres",
            "DeededAcres",
            "CountyName",
            "CountyCode",
        ],
    ),
)
