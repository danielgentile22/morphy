"""Tests for null-safe pandas-aware coercion helpers.

These helpers paper over pandas' habit of storing ``float('nan')`` in
object columns. Coverage focuses on the NaN cases because that's the
whole reason these helpers exist over ``str()`` / ``float()``.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest
from preprocess.normalizers.pandas_coerce import safe_get, safe_str, to_float, to_int

# ── safe_str ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("hello", "hello"),
        ("  trimmed  ", "trimmed"),
        ("", ""),
        (None, ""),
        (math.nan, ""),
        (float("nan"), ""),
        ("nan", ""),       # literal "nan" string from a bad-CSV read
        ("NaN", ""),
        (123, "123"),
        (12.5, "12.5"),
    ],
)
def test_safe_str_handles_every_null_variant(raw, expected):
    assert safe_str(raw) == expected


# ── safe_get ─────────────────────────────────────────────────────────────


def test_safe_get_returns_clean_string_for_present_key():
    row = {"name": "  ALICE  ", "value": 42}
    assert safe_get(row, "name") == "ALICE"
    assert safe_get(row, "value") == "42"


def test_safe_get_returns_empty_for_missing_key():
    assert safe_get({"a": 1}, "b") == ""


def test_safe_get_returns_empty_for_nan_value():
    row = pd.Series({"name": float("nan")})
    assert safe_get(row, "name") == ""


# ── to_float ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("3.14", 3.14),
        ("  3.14  ", 3.14),
        (3.14, 3.14),
        (3, 3.0),
        ("3", 3.0),
        ("-1.5", -1.5),
    ],
)
def test_to_float_parses_valid_inputs(raw, expected):
    assert to_float(raw) == expected


@pytest.mark.parametrize("bad", [None, "", "   ", "abc", math.nan])
def test_to_float_returns_none_on_garbage(bad):
    assert to_float(bad) is None


# ── to_int ───────────────────────────────────────────────────────────────


def test_to_int_via_to_float():
    assert to_int("42") == 42
    assert to_int(42.7) == 42  # truncates per int()
    assert to_int(None) is None
    assert to_int("nope") is None
