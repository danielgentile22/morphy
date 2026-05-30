"""Tests for the carrier-brand rollup (#22, Slice A).

The strings here are REAL ULS licensee names (EN entity_type 'L') drawn from the
#12 normalized parquet — every brand's common variants, the predecessor entities
that map to a current brand, the deliberately-unmapped ambiguous legacy holders,
and the blank/garbage robustness cases. No data on disk is touched.
"""

from __future__ import annotations

import math

import pytest
from preprocess.carrier_brands import (
    ATT,
    BLUEGRASS,
    C_SPIRE,
    CAROLINA_WEST,
    CARRIERS,
    DISH,
    PINE_BELT,
    TMOBILE,
    US_CELLULAR,
    VERIZON,
    carrier_for,
)

# ── mapped: real entity_name variants → expected brand ───────────────────────


@pytest.mark.parametrize(
    "entity_name,expected",
    [
        # AT&T lineage
        ("AT&T Mobility Spectrum, LLC", ATT),
        ("AT&T Mobility LLC", ATT),
        ("New Cingular Wireless PCS, LLC", ATT),
        ("NEW CINGULAR WIRELESS PCS, LLC", ATT),
        ("Cingular Wireless LLC", ATT),
        ("AT&T Wireless Services 3 LLC", ATT),
        ("BellSouth Mobility LLC", ATT),
        ("Southwestern Bell Wireless, LLC", ATT),
        ("Cricket License Company, LLC", ATT),
        ("Leap Wireless International, Inc.", ATT),
        # Verizon lineage
        ("Cellco Partnership", VERIZON),
        ("Cellco Partnership d/b/a Verizon Wireless", VERIZON),
        ("Verizon Wireless of the East LP", VERIZON),
        ("Verizon Americas LLC", VERIZON),
        ("Bell Atlantic Mobile Systems LLC", VERIZON),
        ("AirTouch Cellular", VERIZON),
        ("GTE MOBILNET OF CALIFORNIA LIMITED PARTNERSHIP", VERIZON),
        ("Rural Cellular Corporation", VERIZON),
        # T-Mobile lineage
        ("T-Mobile License LLC", TMOBILE),
        ("T-Mobile USA, Inc.", TMOBILE),
        ("Sprint Spectrum LP", TMOBILE),
        ("SprintCom, Inc.", TMOBILE),
        ("Nextel West Corp.", TMOBILE),
        ("MetroPCS California, LLC", TMOBILE),
        ("VoiceStream PCS BTA License Corp.", TMOBILE),
        ("Powertel Atlanta Licenses, Inc.", TMOBILE),
        ("Clearwire Spectrum Holdings LLC", TMOBILE),
        ("Iowa Wireless Services Holding Corporation", TMOBILE),
        # Dish (brands + documented spectrum subsidiaries / AWS-3 DEs)
        ("DISH Wireless L.L.C.", DISH),
        ("DISH Network LLC", DISH),
        ("EchoStar Corporation", DISH),
        ("Boost Mobile, LLC", DISH),
        ("Northstar Wireless, LLC", DISH),
        ("SNR Wireless LicenseCo, LLC", DISH),
        ("American H Block Wireless L.L.C.", DISH),
        ("Gamma Acquisition L.L.C.", DISH),
        ("DBSD Corporation", DISH),
        # US Cellular
        ("United States Cellular Corporation", US_CELLULAR),
        ("USCC Services, LLC", US_CELLULAR),
        ("USCOC of Tallahassee, Inc.", US_CELLULAR),
        # C-Spire / Cellular South
        ("Cellular South Licenses, LLC", C_SPIRE),
        ("C Spire", C_SPIRE),
        # Named regionals
        ("Carolina West Wireless, Inc.", CAROLINA_WEST),
        ("Pine Belt Cellular, Inc.", PINE_BELT),
        ("Bluegrass Cellular, Inc.", BLUEGRASS),
    ],
)
def test_maps_known_carriers(entity_name, expected):
    brand, is_mapped = carrier_for(None, entity_name)
    assert is_mapped is True
    assert brand == expected
    assert brand in CARRIERS


# ── the tail: unmapped entities return the RAW name + is_mapped=False ─────────


@pytest.mark.parametrize(
    "entity_name",
    [
        "MJ Cellular Company L.L.C.",  # one-off regional LLC, no brand token
        "Palmer Cellular Partnership",
        "Florida RSA #8, Inc.",
        "Gold Creek Cellular of Montana Limited Partnership",
        "The Alaska Wireless Network, LLC",
        "Chicago SMSA LP",  # cellular partnership sold market-by-market
    ],
)
def test_tail_returns_raw_name_unmapped(entity_name):
    brand, is_mapped = carrier_for(None, entity_name)
    assert is_mapped is False
    assert brand == entity_name  # the raw string is preserved for display


def test_alltel_is_deliberately_unmapped():
    """ALLTEL's licenses were split between Verizon (bulk, 2009) and AT&T (a
    divested subset); attributing it to one brand would be a guess. It stays in
    the tail on purpose — see the module docstring."""
    for name in ("ALLTEL Corporation", "Alltel Corporation"):
        brand, is_mapped = carrier_for(None, name)
        assert is_mapped is False
        assert brand == name


# ── robustness: never raise, mirror fips.py's None/flag contract ─────────────


@pytest.mark.parametrize("blank", [None, "", "   ", float("nan"), math.nan])
def test_blank_or_missing_returns_none_unmapped(blank):
    assert carrier_for(None, blank) == (None, False)


@pytest.mark.parametrize("garbage", [12345, 3.14])
def test_does_not_raise_on_non_string_input(garbage):
    # A stray numeric/garbage value must degrade gracefully, not explode.
    brand, is_mapped = carrier_for(None, garbage)
    assert is_mapped is False
    assert brand is not None  # the coerced string, in the tail


def test_raw_name_is_trimmed():
    brand, is_mapped = carrier_for(None, "  Palmer Cellular Partnership  ")
    assert is_mapped is False
    assert brand == "Palmer Cellular Partnership"


# ── signal precedence + signature ────────────────────────────────────────────


def test_callsign_is_accepted_but_name_is_authoritative():
    """callsign is a reserved disambiguator; passing one must not change the
    name-driven result."""
    assert carrier_for("KAAA111", "Cellco Partnership") == (VERIZON, True)
    assert carrier_for(None, "Cellco Partnership") == (VERIZON, True)


def test_normalization_is_punctuation_and_case_insensitive():
    # Same entity, three renderings → same brand.
    for variant in (
        "T-Mobile USA, Inc.",
        "t mobile usa inc",
        "T-MOBILE  USA,   INC.",
    ):
        assert carrier_for(None, variant) == (TMOBILE, True)


@pytest.mark.parametrize(
    "entity_name",
    [
        "Bluegrass Water Utility Operating Company, LLC",
        "Bluegrass Network",
    ],
)
def test_bluegrass_requires_wireless_qualifier(entity_name):
    """'Bluegrass' is a common Kentucky place-name; only a wireless entity maps,
    so unrelated 'Bluegrass <non-telecom>' names stay in the honest tail."""
    brand, is_mapped = carrier_for(None, entity_name)
    assert is_mapped is False
    assert brand == entity_name


def test_metro_does_not_falsely_match_generic_mobile():
    """'T MOBILE' must not fire on an unrelated '... Mobile' entity, and a
    generic regional name stays in the tail."""
    brand, is_mapped = carrier_for(None, "Liberty Mobile Puerto Rico Inc.")
    assert is_mapped is False
    assert brand == "Liberty Mobile Puerto Rico Inc."
