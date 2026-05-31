"""Owner-identity primitives in ``cluster.py``: the column-fallback helper
(``normalized_owner_cols``) and the two distinct hash grains.

These pin the seam extracted behind the owner-clustering modules — the
"prefer the precomputed ``*_norm`` column, else re-normalize the raw column"
fallback now lives in exactly one place, and the within-state vs cross-state
grain distinction is explicit:

  - within-state ``cluster_id`` folds the mailing address into the key
    (conservative — ADR-024);
  - cross-state ``cross_state_owner_key`` is name-only, so a national owner
    collapses to one Lead across regional addresses (ADR-061 / ADR-056).

No real parcel-owner names (TESTING.md §4) — synthetic strings only.
"""

from __future__ import annotations

import pandas as pd
from preprocess.cluster import (
    cluster_id,
    cross_state_owner_key,
    normalize_address,
    normalize_owner_name,
    normalized_owner_cols,
)

# ── normalized_owner_cols: the column-else-map fallback ──────────────────────


def test_normalized_owner_cols_prefers_precomputed_columns():
    # Precomputed *_norm columns are used verbatim, even with no raw columns.
    df = pd.DataFrame(
        {
            "owner_name_norm": ["acme llc", "jane doe"],
            "mailing_addr_norm": ["1 main st", "2 oak ave"],
        }
    )
    name, addr = normalized_owner_cols(df)
    assert list(name) == ["acme llc", "jane doe"]
    assert list(addr) == ["1 main st", "2 oak ave"]


def test_normalized_owner_cols_falls_back_to_raw_normalization():
    # No *_norm columns → re-normalize the raw owner_name / mailing_addr.
    df = pd.DataFrame(
        {
            "owner_name": ["ACME, L.L.C.", "Doe Jane"],
            "mailing_addr": ["1 Main Street", "2 Oak Avenue"],
        }
    )
    name, addr = normalized_owner_cols(df)
    assert list(name) == [normalize_owner_name("ACME, L.L.C."), normalize_owner_name("Doe Jane")]
    assert list(addr) == [normalize_address("1 Main Street"), normalize_address("2 Oak Avenue")]


def test_precomputed_and_raw_paths_return_identical_keys():
    # The producer wrote the *_norm columns with the same normalize_* the
    # fallback uses, so both paths must yield identical key material — this is
    # what keeps the extraction byte-identical wherever a frame carries one
    # form or the other.
    owners = ["ACME, L.L.C.", "Doe Jane", "WEYERHAEUSER CO"]
    addrs = ["1 Main Street", "2 Oak Avenue", "PO Box 9"]
    raw = pd.DataFrame({"owner_name": owners, "mailing_addr": addrs})
    pre = pd.DataFrame(
        {
            "owner_name_norm": [normalize_owner_name(o) for o in owners],
            "mailing_addr_norm": [normalize_address(a) for a in addrs],
        }
    )
    rn, ra = normalized_owner_cols(raw)
    pn, pa = normalized_owner_cols(pre)
    assert list(rn) == list(pn)
    assert list(ra) == list(pa)


def test_blank_precomputed_value_recovers_from_raw_per_row():
    # A row whose precomputed norm is blank but whose raw name normalizes to
    # something is recovered from the raw column — per row, not whole-column.
    df = pd.DataFrame(
        {
            "owner_name_norm": ["acme llc", ""],
            "owner_name": ["ACME LLC", "Jane Doe"],
        }
    )
    name, _ = normalized_owner_cols(df)
    assert list(name) == ["acme llc", normalize_owner_name("Jane Doe")]


def test_missing_columns_yield_empty_series_not_crash():
    # Neither precomputed nor raw column present → empty strings, no crash
    # (a malformed frame degrades instead of throwing).
    df = pd.DataFrame({"unrelated": [1, 2, 3]})
    name, addr = normalized_owner_cols(df)
    assert list(name) == ["", "", ""]
    assert list(addr) == ["", "", ""]


# ── the two grains are explicit and distinct ─────────────────────────────────


def test_within_state_and_cross_state_keys_differ_by_grain():
    # Same owner, two different mailing addresses:
    #   within-state (name + address) → TWO distinct cluster ids,
    #   cross-state  (name only)      → ONE national Lead key.
    owner = normalize_owner_name("AMERICAN TOWERS LLC")
    a1 = normalize_address("1 Mailing Rd")
    a2 = normalize_address("999 Other Ave")
    within_1 = cluster_id(owner, a1)
    within_2 = cluster_id(owner, a2)
    assert within_1 != within_2  # address splits the within-state grain
    assert cross_state_owner_key(owner) == cross_state_owner_key(owner)  # stable
    assert within_2 != cross_state_owner_key(owner)  # name-only collapses them
    assert within_1 != cross_state_owner_key(owner)  # the two grains differ


def test_empty_string_handling_on_both_grains():
    # within-state: empty only when BOTH name and address are empty; an
    # address alone still clusters. cross-state: empty whenever the name is.
    assert cluster_id("", "") == ""
    assert cluster_id("", "1 main st") != ""
    assert cross_state_owner_key("") == ""
