"""Python↔SQL agreement for the owner-cluster key recipe (#257, PRD #253 W5).

The recipe has one home — ``preprocess.cluster`` — which generates the SQL
the compose pre-pass runs. These tests feed representative and edge-case
names/addresses through both forms and require identical keys, so a grain
change that forgets either form fails here (not in production).
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest
from preprocess import cluster

# (raw_name, raw_addr) — representative + edge cases. Non-ASCII pins the
# sha1-over-UTF-8 claim; noise-only names pin the blank-norm path.
CASES = [
    ("Shared Landowner LLC", "123 Main Street"),
    ("GARCÍA JOSÉ", "45 Avenida Ñuñoa"),
    ("Smith & Sons, Inc.", "P.O. Box 42"),
    ("U.S.A.", "1600 Pennsylvania Avenue"),
    ("CROWN CASTLE TOWERS 06-2", ""),
    ("", "789 Lonely Road"),
    ("", ""),
    ("O'Brien-Meyer Family Trust", "12 Ocean Terrace Apt. #3"),
]


@pytest.fixture(scope="module")
def norms() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name_norm": [cluster.normalize_owner_name(n) for n, _ in CASES],
            "addr_norm": [cluster.normalize_address(a) for _, a in CASES],
        }
    )


def test_key_grain_is_pinned() -> None:
    # Lead identity is persistent state — prod rows reference these ids, so a
    # grain change must be a deliberate migration (the ADR-075 pattern with a
    # sidecar map), never a silent constant edit. With Python and SQL both
    # generated from the same constants, agreement tests alone would pass such
    # an edit; these literal vectors are the guard.
    assert cluster.cluster_id("ACME", "1 MAIN ST") == "1176d0591bb0"
    assert cluster.cluster_id("GARCIA JOSE", "") == "4797be24f47f"
    assert (cluster.KEY_SEPARATOR, cluster.KEY_HEX_LEN) == ("|", 12)


def test_generated_sql_matches_python_recipe(norms: pd.DataFrame) -> None:
    python_keys = [cluster.cluster_id(n, a) for n, a in zip(norms["name_norm"], norms["addr_norm"])]
    con = duckdb.connect()
    con.register("rows", norms)
    key_sql = cluster.cluster_id_sql('"name_norm"', '"addr_norm"')
    sql_keys = [r[0] for r in con.execute(f"SELECT {key_sql} FROM rows").fetchall()]
    assert sql_keys == python_keys


def test_prefer_norm_and_routing_match_python_semantics() -> None:
    # The four routing shapes the pre-pass sees: verbatim norms (SQL keys);
    # blank norm with a recoverable raw (→ Python); noise-only raw — the
    # router can't know it normalizes to blank, so it also goes to Python
    # (which keys it '' → excluded); all-blank (stays SQL, keys '').
    rows = pd.DataFrame(
        {
            "owner_name_norm": ["ACME", "", "", ""],
            "owner_name": ["Acme LLC", "Recover Me Inc.", "LLC", ""],
            "mailing_addr_norm": ["1 MAIN ST", "", "", ""],
            "mailing_addr": ["1 Main St", "2 Side Rd", "", ""],
        }
    )
    con = duckdb.connect()
    con.register("p", rows)
    needs_python = cluster.needs_python_sql(
        '"owner_name_norm"', '"owner_name"', '"mailing_addr_norm"', '"mailing_addr"'
    )
    routed = [bool(r[0]) for r in con.execute(f"SELECT {needs_python} FROM p").fetchall()]
    assert routed == [False, True, True, False]

    name_val = cluster.prefer_norm_sql('"owner_name_norm"')
    key_sql = cluster.cluster_id_sql(name_val, cluster.prefer_norm_sql('"mailing_addr_norm"'))
    keys = [r[0] for r in con.execute(f"SELECT {key_sql} FROM p").fetchall()]
    # Row 0 keys in SQL exactly as Python would; rows routed to Python or
    # unrecoverable key '' in the SQL path.
    assert keys[0] == cluster.cluster_id("ACME", "1 MAIN ST")
    assert keys[1:] == ["", "", ""]

    # The recovered row's Python key equals what SQL WOULD produce had the
    # norms been stored — the cross-engine identity the pre-pass relies on.
    recovered_name = cluster.normalize_owner_name("Recover Me Inc.")
    recovered_addr = cluster.normalize_address("2 Side Rd")
    stored = pd.DataFrame({"n": [recovered_name], "a": [recovered_addr]})
    con.register("stored", stored)
    stored_key_sql = cluster.cluster_id_sql('"n"', '"a"')
    sql_key = con.execute(f"SELECT {stored_key_sql} FROM stored").fetchone()[0]
    assert sql_key == cluster.cluster_id(recovered_name, recovered_addr)
