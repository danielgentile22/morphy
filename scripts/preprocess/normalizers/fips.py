"""FIPS canonicalization.

State FIPS, county FIPS, and the derivation rules between them. The
normalize layer relies on these to coerce upstream sources' wildly
inconsistent representations (integer vs string, 3-digit vs 5-digit,
abbreviations, census GEOIDs, etc.) into the project's canonical
zero-padded string form.

Conventions:
  - state FIPS  → 2-digit zero-padded string, e.g. "05"
  - county FIPS → 5-digit zero-padded string (state + county), e.g. "05001"

Returns ``None`` for unparseable / missing input rather than raising —
callers handle the bookkeeping (null state/county is a quality-report
signal, not a fatal error).
"""

from __future__ import annotations

import pandas as pd


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


def _reject_cross_state(county_fips: str, state_fips: str | None) -> str | None:
    """Drop a parsed county FIPS whose state prefix contradicts a known hint.

    A single-state parcel source (e.g. FL ``fdor_nal``) must never yield an
    out-of-state county; when it does — malformed ``CENSUS_BK`` values that
    parse as a bare 5-digit number, e.g. ``27876`` → "state 27" — the value is
    garbage. Returning None lets the caller fall back to the source's known
    state and leave the county null, rather than inventing a bogus county that
    poisons ``states_covered`` and aborts compose (``no state with FIPS '43'``).
    """
    if state_fips is None:
        return county_fips
    hint = canon_state_fips(state_fips)
    if hint is not None and county_fips[:2] != hint:
        return None
    return county_fips


def canon_county_fips(value, *, state_fips: str | None = None) -> str | None:
    """Normalize a county FIPS to a 5-digit string (state + county).

    Accepts:
      - 5-digit string (e.g. '37075')
      - 3-digit string + state_fips arg (e.g. '075', state_fips='37')
      - integer 75 with state_fips='37'
      - census tract / block GEOID (≥10 digits, e.g. '120010019081') —
        the county FIPS is positions 0-4. Used by FDOR PAR shapefiles,
        whose only county identifier is the CENSUS_BK field.

    When ``state_fips`` is given, a result whose state prefix disagrees with it
    is rejected (returns None) — a single-state source can't have out-of-state
    counties, so a mismatch means the raw value was unparseable garbage.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s:
        return None
    # Census GEOID: slice rather than int-parse so a leading-zero state
    # code (e.g. Alabama '01...') isn't lost.
    if s.isdigit() and len(s) >= 10:
        return _reject_cross_state(s[:5], state_fips)
    try:
        n = int(float(s))
    except (TypeError, ValueError):
        return None

    if 1000 <= n <= 99999:
        return _reject_cross_state(f"{n:05d}", state_fips)
    if 0 <= n <= 999:
        if state_fips is None:
            return None
        sf = canon_state_fips(state_fips)
        if sf is None:
            return None
        return f"{sf}{n:03d}"
    return None


def state_fips_from_county_fips(county_fips: str | None) -> str | None:
    """Slice the leading 2-digit state code off a canonical 5-digit county FIPS."""
    if not county_fips:
        return None
    s = str(county_fips).strip()
    if len(s) >= 5:
        return s[:2]
    return None
