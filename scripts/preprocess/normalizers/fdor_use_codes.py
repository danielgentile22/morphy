"""Florida DOR land-use code → text lookup (audit fix E4).

The FDOR NAL tax roll's ``DOR_UC`` field is a numeric land-use code (000–099)
documented in the FL DOR NAL/SDF/NAP User's Guide (Field 8). The parcel adapter
surfaced the bare code as the land-use *description*; this decodes it to the
documented text so a church (071) reads differently from a private school (072).

Pure + isolated by design — a single dict + one accessor, no pipeline deps, so
the mapping is unit-testable without running the normalizer. Florida-only: MT/WV
already map a real descriptive column, and AR has no published code dictionary
(INHERENT in the audit ledger, INH-6).

Source: FL DOR 2025 NAL/SDF/NAP User's Guide, "Land Use / DOR Use Codes" table.
"""

from __future__ import annotations

# DOR use code (0–99) → documented description. The published statewide table;
# county PAOs may add local codes ≥ 100 (returned as None → caller falls back to
# the bare code rather than mislabeling).
DOR_USE_CODES: dict[int, str] = {
    0: "Vacant residential",
    1: "Single family",
    2: "Mobile homes",
    3: "Multi-family (10+ units)",
    4: "Condominium",
    5: "Cooperative",
    6: "Retirement homes",
    7: "Miscellaneous residential",
    8: "Multi-family (<10 units)",
    9: "Residential common element / common area",
    10: "Vacant commercial",
    11: "Stores, one story",
    12: "Mixed use (store and office / residential)",
    13: "Department stores",
    14: "Supermarkets",
    15: "Regional shopping malls",
    16: "Community shopping centers",
    17: "Office buildings, one story",
    18: "Office buildings, multi-story",
    19: "Professional service buildings",
    20: "Airports, terminals, piers, marinas",
    21: "Restaurants, cafeterias",
    22: "Drive-in restaurants",
    23: "Financial institutions",
    24: "Insurance company offices",
    25: "Repair service shops",
    26: "Service stations",
    27: "Auto sales, repair, storage",
    28: "Parking lots, mobile home parks",
    29: "Wholesale outlets, produce houses",
    30: "Florists, greenhouses",
    31: "Drive-in theaters, open stadiums",
    32: "Enclosed theaters, auditoriums",
    33: "Nightclubs, bars, lounges",
    34: "Bowling alleys, skating rinks, arenas",
    35: "Tourist attractions, fairgrounds",
    36: "Camps",
    37: "Race tracks",
    38: "Golf courses, driving ranges",
    39: "Hotels, motels",
    40: "Vacant industrial",
    41: "Light manufacturing",
    42: "Heavy industrial",
    43: "Lumber yards, sawmills, planing mills",
    44: "Packing plants",
    45: "Canneries, bottlers, distilleries",
    46: "Other food processing",
    47: "Mineral processing",
    48: "Warehousing, distribution terminals",
    49: "Open storage, junk yards",
    50: "Improved agricultural",
    51: "Cropland soil class I",
    52: "Cropland soil class II",
    53: "Cropland soil class III",
    54: "Timberland, site index 90+",
    55: "Timberland, site index 80–89",
    56: "Timberland, site index 70–79",
    57: "Timberland, site index 60–69",
    58: "Timberland, site index 50–59",
    59: "Timberland, not classified by site index",
    60: "Grazing land soil class I",
    61: "Grazing land soil class II",
    62: "Grazing land soil class III",
    63: "Grazing land soil class IV",
    64: "Grazing land soil class V",
    65: "Grazing land soil class VI",
    66: "Orchard groves, citrus",
    67: "Poultry, bees, fish, rabbits",
    68: "Dairies, feed lots",
    69: "Ornamentals, miscellaneous agricultural",
    70: "Vacant institutional",
    71: "Churches",
    72: "Private schools and colleges",
    73: "Privately owned hospitals",
    74: "Homes for the aged",
    75: "Orphanages, non-profit / charitable services",
    76: "Mortuaries, cemeteries, crematoriums",
    77: "Clubs, lodges, union halls",
    78: "Sanitariums, convalescent and rest homes",
    79: "Cultural organizations, facilities",
    80: "Vacant governmental",
    81: "Military",
    82: "Forest, parks, recreational areas",
    83: "Public county schools",
    84: "Colleges (public)",
    85: "Hospitals (public)",
    86: "County (other than schools, colleges, hospitals)",
    87: "State (other than military, forest, parks)",
    88: "Federal (other than military, forest, parks)",
    89: "Municipal (other than parks, recreational)",
    90: "Leasehold interests (government-owned, leased)",
    91: "Utility (gas, electric, telephone, water, pipelines)",
    92: "Mining, petroleum, gas lands",
    93: "Subsurface rights",
    94: "Rights-of-way, streets, roads, ditches",
    95: "Rivers, lakes, submerged lands",
    96: "Sewage disposal, waste land, marsh, swamp",
    97: "Outdoor recreational / parkland",
    98: "Centrally assessed",
    99: "Acreage not zoned agricultural",
}


def land_use_desc(code: object) -> str | None:
    """Decode a DOR use code to its documented description, or None if unknown.

    Tolerant of the raw shapes the code arrives in — ``"001"``, ``"01"``,
    ``"1"``, ``1``, ``1.0`` all map to code 1. Blank, non-numeric, or
    out-of-table (local codes ≥ 100) returns None so the caller can fall back
    to the bare code instead of inventing a label.
    """
    if code is None:
        return None
    s = str(code).strip()
    if not s:
        return None
    try:
        n = int(float(s))
    except ValueError:
        return None
    return DOR_USE_CODES.get(n)
