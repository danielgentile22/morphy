"""State registry: FIPS, abbreviation, name, bounding box.

Bboxes are derived from Census state polygons (US Cartographic Boundary
Files). They're rough conservative envelopes — used for spatial
pre-filtering of national datasets, not for legal boundaries.

The Composer uses each state's FIPS to filter normalized data by the
`state_fips` column on every canonical record. The bbox is only used
when a normalized record is missing state_fips (rare — fallback).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class StateGeography:
    fips: str       # '37'
    abbr: str       # 'NC'
    name: str       # 'North Carolina'
    bbox: tuple[float, float, float, float]   # (minx, miny, maxx, maxy) in EPSG:4326


# Bboxes from Census TIGER state polygons, rounded outward slightly.
STATES: dict[str, StateGeography] = {
    "01": StateGeography("01", "AL", "Alabama", (-88.47, 30.14, -84.89, 35.01)),
    "02": StateGeography("02", "AK", "Alaska", (-179.15, 51.21, 179.78, 71.44)),
    "04": StateGeography("04", "AZ", "Arizona", (-114.82, 31.33, -109.05, 37.01)),
    "05": StateGeography("05", "AR", "Arkansas", (-94.62, 33.00, -89.64, 36.50)),
    "06": StateGeography("06", "CA", "California", (-124.48, 32.53, -114.13, 42.01)),
    "08": StateGeography("08", "CO", "Colorado", (-109.06, 36.99, -102.04, 41.00)),
    "09": StateGeography("09", "CT", "Connecticut", (-73.73, 40.98, -71.78, 42.05)),
    "10": StateGeography("10", "DE", "Delaware", (-75.79, 38.45, -75.05, 39.84)),
    "11": StateGeography("11", "DC", "District of Columbia", (-77.12, 38.79, -76.91, 38.99)),
    "12": StateGeography("12", "FL", "Florida", (-87.63, 24.40, -79.97, 31.01)),
    "13": StateGeography("13", "GA", "Georgia", (-85.61, 30.36, -80.84, 35.00)),
    "15": StateGeography("15", "HI", "Hawaii", (-178.45, 18.91, -154.81, 28.40)),
    "16": StateGeography("16", "ID", "Idaho", (-117.24, 41.99, -111.04, 49.00)),
    "17": StateGeography("17", "IL", "Illinois", (-91.51, 36.97, -87.50, 42.51)),
    "18": StateGeography("18", "IN", "Indiana", (-88.10, 37.77, -84.78, 41.76)),
    "19": StateGeography("19", "IA", "Iowa", (-96.64, 40.38, -90.14, 43.50)),
    "20": StateGeography("20", "KS", "Kansas", (-102.05, 36.99, -94.59, 40.00)),
    "21": StateGeography("21", "KY", "Kentucky", (-89.57, 36.50, -81.96, 39.15)),
    "22": StateGeography("22", "LA", "Louisiana", (-94.04, 28.93, -88.82, 33.02)),
    "23": StateGeography("23", "ME", "Maine", (-71.08, 43.06, -66.94, 47.46)),
    "24": StateGeography("24", "MD", "Maryland", (-79.49, 37.89, -75.05, 39.72)),
    "25": StateGeography("25", "MA", "Massachusetts", (-73.51, 41.24, -69.93, 42.89)),
    "26": StateGeography("26", "MI", "Michigan", (-90.42, 41.70, -82.41, 48.31)),
    "27": StateGeography("27", "MN", "Minnesota", (-97.24, 43.50, -89.49, 49.39)),
    "28": StateGeography("28", "MS", "Mississippi", (-91.66, 30.17, -88.10, 35.01)),
    "29": StateGeography("29", "MO", "Missouri", (-95.78, 35.99, -89.10, 40.62)),
    "30": StateGeography("30", "MT", "Montana", (-116.06, 44.36, -104.04, 49.00)),
    "31": StateGeography("31", "NE", "Nebraska", (-104.06, 39.99, -95.31, 43.00)),
    "32": StateGeography("32", "NV", "Nevada", (-120.01, 35.00, -114.03, 42.00)),
    "33": StateGeography("33", "NH", "New Hampshire", (-72.56, 42.69, -70.61, 45.31)),
    "34": StateGeography("34", "NJ", "New Jersey", (-75.56, 38.93, -73.89, 41.36)),
    "35": StateGeography("35", "NM", "New Mexico", (-109.05, 31.33, -103.00, 37.00)),
    "36": StateGeography("36", "NY", "New York", (-79.77, 40.50, -71.86, 45.02)),
    "37": StateGeography("37", "NC", "North Carolina", (-84.32, 33.84, -75.46, 36.59)),
    "38": StateGeography("38", "ND", "North Dakota", (-104.05, 45.94, -96.55, 49.00)),
    "39": StateGeography("39", "OH", "Ohio", (-84.82, 38.40, -80.52, 42.33)),
    "40": StateGeography("40", "OK", "Oklahoma", (-103.00, 33.62, -94.43, 37.00)),
    "41": StateGeography("41", "OR", "Oregon", (-124.57, 41.99, -116.46, 46.27)),
    "42": StateGeography("42", "PA", "Pennsylvania", (-80.52, 39.72, -74.69, 42.27)),
    "44": StateGeography("44", "RI", "Rhode Island", (-71.91, 41.15, -71.12, 42.02)),
    "45": StateGeography("45", "SC", "South Carolina", (-83.36, 32.03, -78.55, 35.22)),
    "46": StateGeography("46", "SD", "South Dakota", (-104.06, 42.48, -96.44, 45.95)),
    "47": StateGeography("47", "TN", "Tennessee", (-90.31, 34.98, -81.65, 36.68)),
    "48": StateGeography("48", "TX", "Texas", (-106.65, 25.84, -93.51, 36.50)),
    "49": StateGeography("49", "UT", "Utah", (-114.05, 36.99, -109.04, 42.00)),
    "50": StateGeography("50", "VT", "Vermont", (-73.44, 42.73, -71.46, 45.02)),
    "51": StateGeography("51", "VA", "Virginia", (-83.68, 36.54, -75.24, 39.47)),
    "53": StateGeography("53", "WA", "Washington", (-124.85, 45.54, -116.92, 49.00)),
    "54": StateGeography("54", "WV", "West Virginia", (-82.65, 37.20, -77.72, 40.64)),
    "55": StateGeography("55", "WI", "Wisconsin", (-92.89, 42.49, -86.81, 47.31)),
    "56": StateGeography("56", "WY", "Wyoming", (-111.06, 40.99, -104.05, 45.01)),
    # Territories included for completeness — most sources have no data here
    "60": StateGeography("60", "AS", "American Samoa", (-171.09, -14.55, -168.13, -11.05)),
    "66": StateGeography("66", "GU", "Guam", (144.55, 13.18, 145.01, 13.71)),
    "69": StateGeography("69", "MP", "Northern Mariana Islands", (144.86, 14.10, 146.06, 20.55)),
    "72": StateGeography("72", "PR", "Puerto Rico", (-67.95, 17.88, -65.22, 18.52)),
    "78": StateGeography("78", "VI", "U.S. Virgin Islands", (-65.09, 17.67, -64.56, 18.41)),
}


def get_state(fips: str) -> StateGeography:
    if fips not in STATES:
        raise KeyError(f"no state with FIPS {fips!r}")
    return STATES[fips]


def get_state_by_abbr(abbr: str) -> StateGeography:
    abbr_u = abbr.upper()
    for s in STATES.values():
        if s.abbr == abbr_u:
            return s
    raise KeyError(f"no state with abbreviation {abbr!r}")


def all_states() -> list[StateGeography]:
    return list(STATES.values())


def states_iter() -> Iterator[StateGeography]:
    yield from STATES.values()


def states_with_normalized_data(preprocess_manifest: dict) -> list[StateGeography]:
    """Return states for which at least one normalized parcel layer exists.

    Looks at preprocess_manifest['normalized'][*]['states_covered'] when the
    field is populated by parcel Normalizers; falls back to listing every
    state if no parcel manifest is present (so the dropdown isn't empty
    on first run).
    """
    covered: set[str] = set()
    norm = (preprocess_manifest or {}).get("normalized", {})
    for entry in norm.values():
        for fips in (entry or {}).get("states_covered", []) or []:
            if fips in STATES:
                covered.add(fips)
    if not covered:
        # Fallback so the UI dropdown shows something useful on first run.
        return all_states()
    return [STATES[f] for f in sorted(covered)]
