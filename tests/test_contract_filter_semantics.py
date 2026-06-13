"""Cross-language contract: owner filter semantics, SQL side (PRD #137).

The frontend's ``FILTER_FIELDS`` registry projects each filter two ways from one
definition: a DuckDB WHERE body (``composeOwnerWhere``) and a JS predicate
(``matchesOwner``). ``app/tests/unit/contract-filter-semantics.test.ts`` pins the
JS side and the generated SQL string; this test closes the loop by *executing*
that generated SQL in a real DuckDB over the same synthetic owners and asserting
the selected ids match the fixture's ``expected_ids``.

Both sides read ``contracts/filter_semantics.json``. A real SQL-vs-predicate
disagreement surfaces here as a red test (it did not at authoring time — every
case agrees); per PRD #137 that would be a bug to file, not a fixture to fudge.

DuckDB is the pipeline's compose engine (PRD #135) and a hard test dependency
(see ``tests/test_duckdb_equivalence.py``), so this runs in the normal pytest gate.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[1] / "contracts" / "filter_semantics.json").read_text()
)


def _owners_connection() -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB with the synthetic ``owners`` table, typed from the
    fixture's ``owner_columns`` (so a new owner field is a one-file edit)."""
    cols = CONTRACT["owner_columns"]
    con = duckdb.connect()
    ddl = ", ".join(f"{name} {sql_type}" for name, sql_type in cols.items())
    con.execute(f"CREATE TABLE owners ({ddl})")
    rows = [[owner[name] for name in cols] for owner in CONTRACT["owners"]]
    placeholders = ", ".join(["?"] * len(cols))
    con.executemany(f"INSERT INTO owners VALUES ({placeholders})", rows)
    return con


@pytest.fixture(scope="module")
def con() -> Iterator[duckdb.DuckDBPyConnection]:
    connection = _owners_connection()
    yield connection
    connection.close()


def test_every_owner_has_a_unique_id() -> None:
    ids = [o["id"] for o in CONTRACT["owners"]]
    assert len(ids) == len(set(ids)), "fixture owner ids must be unique"


@pytest.mark.parametrize("case", CONTRACT["cases"], ids=lambda c: c["name"])
def test_generated_sql_selects_expected_ids(con: duckdb.DuckDBPyConnection, case: dict) -> None:
    where = case["where"].strip()
    sql = f"SELECT id FROM owners{(' WHERE ' + where) if where else ''}"
    selected = sorted(row[0] for row in con.execute(sql).fetchall())
    assert selected == sorted(case["expected_ids"])
