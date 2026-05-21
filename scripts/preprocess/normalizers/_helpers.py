"""Shared helpers for Normalizers.

DMS→decimal, FIPS canonicalisation, address normalisation, pipe-delimited
.dat reader (with FCC defensiveness), state-fips inference, etc.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger("preprocess.normalizers")


# ── DMS → decimal degrees ─────────────────────────────────────────────────────


def dms_to_decimal(deg, minutes, seconds, direction) -> float | None:
    """Convert separate degrees/minutes/seconds/direction fields → decimal."""
    try:
        d = float(deg) if deg not in (None, "", "nan") else None
        m = float(minutes) if minutes not in (None, "", "nan") else 0.0
        s = float(seconds) if seconds not in (None, "", "nan") else 0.0
    except (TypeError, ValueError):
        return None
    if d is None:
        return None
    val = abs(d) + m / 60.0 + s / 3600.0
    if direction in ("S", "W"):
        val = -val
    return val


# ── FIPS canonicalisation ─────────────────────────────────────────────────────


def canon_state_fips(value) -> str | None:
    """Normalize a state FIPS / abbreviation to a 2-digit string."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip().upper()
    if not s:
        return None
    # Numeric forms
    try:
        n = int(float(s))
        return f"{n:02d}"
    except (TypeError, ValueError):
        pass
    # Abbreviation lookup
    from ..geographies import STATES

    for st in STATES.values():
        if st.abbr == s:
            return st.fips
    return None


def canon_county_fips(value, *, state_fips: str | None = None) -> str | None:
    """Normalize a county FIPS to a 5-digit string (state + county).

    Accepts:
      - 5-digit string (e.g. '37075')
      - 3-digit string + state_fips arg (e.g. '075', state_fips='37')
      - integer 75 with state_fips='37'
      - census tract / block GEOID (≥10 digits, e.g. '120010019081') —
        the county FIPS is positions 0-4. Used by FDOR PAR shapefiles,
        whose only county identifier is the CENSUS_BK field.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s:
        return None
    # Census GEOID: slice rather than int-parse so a leading-zero state
    # code (e.g. Alabama '01...') isn't lost.
    if s.isdigit() and len(s) >= 10:
        return s[:5]
    try:
        n = int(float(s))
    except (TypeError, ValueError):
        return None

    if 1000 <= n <= 99999:
        return f"{n:05d}"
    if 0 <= n <= 999:
        if state_fips is None:
            return None
        sf = canon_state_fips(state_fips)
        if sf is None:
            return None
        return f"{sf}{n:03d}"
    return None


def state_fips_from_county_fips(county_fips: str | None) -> str | None:
    if not county_fips:
        return None
    s = str(county_fips).strip()
    if len(s) >= 5:
        return s[:2]
    return None


# ── Pipe-delimited reader (for FCC ASR + ULS .dat files) ─────────────────────


def read_pipe_dat(
    path: Path,
    columns: list[str],
    record_type: str | None = None,
    *,
    encoding: str = "latin-1",
) -> pd.DataFrame:
    """Read a pipe-delimited .dat file with a known column list.

    If ``record_type`` is given, rows whose first field doesn't match are
    dropped (defensive guard against stray header/footer rows or mixed-record
    files). All columns are read as strings.
    """
    if not path.exists():
        raise FileNotFoundError(f"missing .dat file: {path}")
    log.debug("reading %s (%d cols)", path.name, len(columns))
    df = pd.read_csv(
        path,
        sep="|",
        header=None,
        names=columns,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
        engine="python",
        on_bad_lines="warn",
        encoding=encoding,
        quoting=csv.QUOTE_NONE,
    )
    if record_type and columns and columns[0] == "record_type":
        before = len(df)
        df = df[df["record_type"] == record_type].copy()
        if len(df) != before:
            log.warning("dropped %d non-%s rows from %s", before - len(df), record_type, path.name)
    return df


def read_pipe_dat_indexed(
    path: Path,
    fields: dict[int, str],
    record_type: str | None = None,
    *,
    encoding: str = "latin-1",
) -> pd.DataFrame:
    """Like read_pipe_dat but read only specific column indices.

    fields is {column_index: friendly_name}. Index 0 is the record-type column.
    If record_type is given, index 0 should be in fields and gets dropped after
    filtering.
    """
    if not path.exists():
        raise FileNotFoundError(f"missing .dat file: {path}")
    df = pd.read_csv(
        path,
        sep="|",
        header=None,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
        engine="python",
        on_bad_lines="warn",
        encoding=encoding,
        quoting=csv.QUOTE_NONE,
        usecols=list(fields.keys()),
    )
    df = df.rename(columns={k: v for k, v in fields.items()})
    if record_type and "_record_type" in df.columns:
        before = len(df)
        df = df[df["_record_type"] == record_type].drop(columns=["_record_type"])
        if len(df) != before:
            log.warning("dropped %d non-%s rows from %s", before - len(df), record_type, path.name)
    return df


# ── Address normalization ─────────────────────────────────────────────────────


def combine_address(*parts) -> str:
    """Combine street/city/state/zip into a one-line address. Skips blanks."""
    bits = []
    for p in parts:
        if p is None:
            continue
        if isinstance(p, float) and pd.isna(p):
            continue
        s = str(p).strip()
        if s:
            bits.append(s)
    return ", ".join(bits)


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
    f = to_float(x)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError):
        return None


def safe_str(x) -> str:
    """Cast a possibly-None / possibly-NaN value to a clean stripped string.

    Pandas' object columns often contain float NaN even for nominally-string
    fields. ``row.get('foo') or ''`` returns the NaN unchanged (NaN is truthy
    as a float). This helper returns '' for all null variants.
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
    """Like row.get(key) but always returns a clean stripped string."""
    try:
        v = row[key]
    except (KeyError, IndexError):
        return ""
    return safe_str(v)
