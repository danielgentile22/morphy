"""Null-safe pandas-aware value coercion.

Pandas' object columns often contain ``float('nan')`` even where the
nominal dtype is string — so a naive ``str(x)`` produces the literal
``"nan"``, and ``row.get(k) or ''`` returns NaN unchanged (NaN is
truthy as a float). These helpers paper over that for the (many)
normalize-time call sites that just want "the trimmed string value
or empty" / "a float or None".
"""

from __future__ import annotations

import pandas as pd


def to_float(x) -> float | None:
    """Best-effort float conversion. Returns None for nulls / unparseable."""
    if x is None:
        return None
    if isinstance(x, float) and pd.isna(x):
        return None
    try:
        s = str(x).strip()
        if not s:
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def to_int(x) -> int | None:
    """Best-effort int conversion via ``to_float``. Returns None on failure."""
    f = to_float(x)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError):
        return None


def safe_str(x) -> str:
    """Cast a possibly-None / possibly-NaN value to a clean stripped string.

    Returns '' for every null variant (None, NaN, the literal "nan").
    """
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() == "nan":
        return ""
    return s


def safe_get(row, key) -> str:
    """Like ``row.get(key)`` but always returns a clean stripped string."""
    try:
        v = row[key]
    except (KeyError, IndexError):
        return ""
    return safe_str(v)
