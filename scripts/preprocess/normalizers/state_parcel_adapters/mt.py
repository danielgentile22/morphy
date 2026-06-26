"""Montana — Cadastral OWNERPARCEL shapefile.

Verified against the OWNERPARCEL.shp .dbf schema. Shapefile 10-char
column truncation: OwnerAddress→OwnerAddre, TotalLandValue→TotalLandV,
OwnerZipCode→OwnerZipCo, etc.

The layer identifies counties only by name (CountyName); there is no
FIPS column. ``county_resolver`` maps the uppercased name to its
5-digit FIPS.
"""

from __future__ import annotations

import re

import geopandas as gpd

from ..state_parcels import ParcelAdapter

_ZIP_RE = re.compile(r"(\d{5}(?:-\d{4})?)\s*$")
_STATE_RE = re.compile(r"[,\s]([A-Za-z]{2})\s*$")


def _parse_city_state_zip(value: object) -> tuple[str, str, str]:
    """Split MT Cadastral's combined ``CityStateZ`` into (city, state, zip).

    Parsed from the right so it tolerates the raw's format drift
    ("MISSOULA, MT 59801", "MISSOULA MT 59801", "GREAT FALLS MT 59405-1234").
    A standalone trailing 2-letter token is the state and a trailing 5(-4)-digit
    token is the zip; everything else is the city. Missing parts come back ''.
    """
    s = ("" if value is None else str(value)).strip().rstrip(",").strip()
    if not s:
        return "", "", ""
    zip_ = ""
    m = _ZIP_RE.search(s)
    if m:
        zip_ = m.group(1)
        s = s[: m.start()].strip()
    state = ""
    m2 = _STATE_RE.search(s)
    if m2:
        state = m2.group(1).upper()
        s = s[: m2.start()].strip()
    return s.rstrip(",").strip(), state, zip_


def _split_situs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """E12: split the combined CityStateZ (carried into situs_city by the
    field_map) into the three situs sub-fields."""
    gdf = gdf.copy()
    parts = [_parse_city_state_zip(v) for v in gdf["situs_city"]]
    gdf["situs_city"] = [p[0] for p in parts]
    gdf["situs_state"] = [p[1] for p in parts]
    gdf["situs_zip"] = [p[2] for p in parts]
    return gdf


# County name → 5-digit FIPS. MT FIPS are alphabetical, odd codes 30001–30111.
MT_COUNTY_NAME_TO_FIPS: dict[str, str] = {
    "BEAVERHEAD": "30001",
    "BIG HORN": "30003",
    "BLAINE": "30005",
    "BROADWATER": "30007",
    "CARBON": "30009",
    "CARTER": "30011",
    "CASCADE": "30013",
    "CHOUTEAU": "30015",
    "CUSTER": "30017",
    "DANIELS": "30019",
    "DAWSON": "30021",
    "DEER LODGE": "30023",
    "FALLON": "30025",
    "FERGUS": "30027",
    "FLATHEAD": "30029",
    "GALLATIN": "30031",
    "GARFIELD": "30033",
    "GLACIER": "30035",
    "GOLDEN VALLEY": "30037",
    "GRANITE": "30039",
    "HILL": "30041",
    "JEFFERSON": "30043",
    "JUDITH BASIN": "30045",
    "LAKE": "30047",
    "LEWIS AND CLARK": "30049",
    "LIBERTY": "30051",
    "LINCOLN": "30053",
    "MCCONE": "30055",
    "MADISON": "30057",
    "MEAGHER": "30059",
    "MINERAL": "30061",
    "MISSOULA": "30063",
    "MUSSELSHELL": "30065",
    "PARK": "30067",
    "PETROLEUM": "30069",
    "PHILLIPS": "30071",
    "PONDERA": "30073",
    "POWDER RIVER": "30075",
    "POWELL": "30077",
    "PRAIRIE": "30079",
    "RAVALLI": "30081",
    "RICHLAND": "30083",
    "ROOSEVELT": "30085",
    "ROSEBUD": "30087",
    "SANDERS": "30089",
    "SHERIDAN": "30091",
    "SILVER BOW": "30093",
    "STILLWATER": "30095",
    "SWEET GRASS": "30097",
    "TETON": "30099",
    "TOOLE": "30101",
    "TREASURE": "30103",
    "VALLEY": "30105",
    "WHEATLAND": "30107",
    "WIBAUX": "30109",
    "YELLOWSTONE": "30111",
}


def _resolve_mt_county(name: str) -> str | None:
    return MT_COUNTY_NAME_TO_FIPS.get(name.strip().upper()) if name else None


MT_CADASTRAL_PARCELS_ADAPTER = ParcelAdapter(
    source_id="mt_cadastral_parcels",
    state_fips="30",
    field_map={
        "parcel_id": ["PARCELID"],
        "parcel_id_full": ["PARCELID"],
        "owner_name": ["OwnerName"],
        "owner_name_2": ["DbaName"],
        "mailing_addr": ["OwnerAddre"],
        "mailing_city": ["OwnerCity"],
        "mailing_state": ["OwnerState"],
        "mailing_zip": ["OwnerZipCo"],
        "situs_addr": ["AddressLin"],
        # CityStateZ is a combined "city state zip" — carried into situs_city
        # here, then split into city/state/zip by the _split_situs post_map (E12).
        "situs_city": ["CityStateZ"],
        "acreage": ["GISAcres"],
        "land_value": ["TotalLandV"],
        "improvement_value": ["TotalBuild"],
        "assessed_value": ["TotalValue"],
        "land_use_code": ["PropType"],
        "land_use_desc": ["PropType"],
        "county_fips": ["CountyName"],
    },
    county_resolver=_resolve_mt_county,
    post_map=_split_situs,
)
