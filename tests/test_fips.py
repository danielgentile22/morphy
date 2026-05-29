"""Tests for FIPS canonicalization.

FIPS handling has historically been the source of subtle bugs — leading
zeros lost on integer conversion, 3-digit county codes orphaned from
their state, census GEOIDs sliced wrong. These tests pin every shape
the normalizers actually feed in.
"""

from __future__ import annotations

import math

import pytest
from preprocess.normalizers.fips import (
    canon_county_fips,
    canon_state_fips,
    state_fips_from_county_fips,
)

# ── canon_state_fips ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("05", "05"),  # already canonical
        ("5", "05"),  # integer-as-string, pad to 2
        (5, "05"),  # native int
        (5.0, "05"),  # native float
        ("AR", "05"),  # abbreviation
        ("ar", "05"),  # lowercased abbreviation
        ("Mt", "30"),  # mixed-case abbreviation
        ("37", "37"),  # already canonical, NC
        (37, "37"),
    ],
)
def test_canon_state_fips_parses_expected_shapes(raw, expected):
    assert canon_state_fips(raw) == expected


@pytest.mark.parametrize("bad", [None, "", "   ", "XX", "NotAState", float("nan")])
def test_canon_state_fips_returns_none_on_garbage(bad):
    assert canon_state_fips(bad) is None


# ── canon_county_fips ────────────────────────────────────────────────────


def test_canon_county_fips_passes_through_five_digit_string():
    assert canon_county_fips("37075") == "37075"
    assert canon_county_fips("05001") == "05001"


def test_canon_county_fips_pads_three_digit_with_state_fips_arg():
    """The AR DataScout layer ships CountyFips as '001'; the normalizer
    passes state_fips='05' alongside."""
    assert canon_county_fips("001", state_fips="05") == "05001"
    assert canon_county_fips("75", state_fips="37") == "37075"
    assert canon_county_fips(75, state_fips="37") == "37075"


def test_canon_county_fips_returns_none_when_three_digit_lacks_state():
    """A 3-digit county is ambiguous without the state. Returning None
    keeps the row in the normalize output (with null county_fips)
    rather than silently picking a wrong state."""
    assert canon_county_fips("001") is None
    assert canon_county_fips(75) is None


def test_canon_county_fips_slices_geoid_to_five_digits():
    """FDOR NAL ships CENSUS_BK as a 12-digit census-block GEOID; the
    county FIPS is positions 0..4. Critical edge case — slicing
    rather than int-parsing preserves leading-zero state codes."""
    assert canon_county_fips("120010001001") == "12001"  # Alachua, FL
    assert canon_county_fips("120869812003") == "12086"  # Miami-Dade, FL
    assert canon_county_fips("010010001001") == "01001"  # Autauga, AL (leading-zero state)


def test_canon_county_fips_via_state_abbreviation_arg():
    """state_fips arg accepts an abbreviation too (canon_state_fips
    runs on it first)."""
    assert canon_county_fips("001", state_fips="AR") == "05001"


@pytest.mark.parametrize("bad", [None, "", "   ", "abc", float("nan")])
def test_canon_county_fips_returns_none_on_garbage(bad):
    assert canon_county_fips(bad) is None


def test_canon_county_fips_nan_with_state_fips_still_none():
    assert canon_county_fips(math.nan, state_fips="05") is None


# ── state_fips_from_county_fips ─────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("37075", "37"),
        ("05001", "05"),
        ("12086", "12"),
        ("01001", "01"),  # leading-zero state preserved
    ],
)
def test_state_fips_from_county_fips_slices_leading_two(raw, expected):
    assert state_fips_from_county_fips(raw) == expected


@pytest.mark.parametrize("bad", [None, "", "abc", "1234"])  # last is too short
def test_state_fips_from_county_fips_returns_none_when_invalid(bad):
    assert state_fips_from_county_fips(bad) is None
