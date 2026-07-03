"""Tests for scripts/preprocess/national_towers.py — the combined towers.json.

The combined ``composite/towers.json`` must be *equivalent* to the
per-state union the map app produces today: the same towers with the
same field values, projected through the same aliases/casts/drop the
client's DuckDB tower query (`loadTowerPoints`) runs. These tests pin
that equivalence against a DuckDB-free reference union (prior art:
tests/test_duckdb_equivalence.py), plus the 7-field schema and the
schema-version envelope. Tiny on-disk fixtures — never the real data.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from preprocess.cluster import cross_state_owner_key, normalize_owner_name
from preprocess.national_towers import (
    TOWERS_FILENAME,
    TOWERS_SCHEMA_VERSION,
    build_national_towers,
)

# The fields the frontend TowerRow / rowsToFeatureCollection consume — the 7
# slim columns plus the baked owner Lead key `cid` (#166), plus (v2, audit
# M-b/M-c) date_built and the ASR tower-owner contact block.
ROW_FIELDS = {
    "asr",
    "owner",
    "cid",
    "height_m",
    "state",
    "active",
    "lat",
    "lon",
    "date_built",
    "tower_owner",
    "tower_owner_street",
    "tower_owner_city",
    "tower_owner_state",
    "tower_owner_zip",
    "tower_owner_phone",
}


def _cid(owner: str | None) -> str:
    """The owner Lead key the builder bakes — the canonical preprocess recipe
    (same hash the client's ownerNameToClusterId produces)."""
    return cross_state_owner_key(normalize_owner_name(owner))


def _make_towers_parquet(path: Path, rows: list[dict]) -> None:
    """A tiny composite towers.parquet fixture.

    Carries the slim union columns plus extra columns the projection must
    drop (``structure_type_desc``, ``carriers``), with explicit nullable
    types so a null surfaces as a real null (not NaN) on read-back.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "asr_number": pa.array([r.get("asr_number") for r in rows], pa.string()),
            "parcel_owner": pa.array([r.get("parcel_owner") for r in rows], pa.string()),
            "height_m": pa.array([r.get("height_m") for r in rows], pa.float64()),
            "state": pa.array([r.get("state") for r in rows], pa.string()),
            "is_active": pa.array([r.get("is_active") for r in rows], pa.bool_()),
            "lat": pa.array([r.get("lat") for r in rows], pa.float64()),
            "lon": pa.array([r.get("lon") for r in rows], pa.float64()),
            # v2 (audit M-b/M-c): build date + the ASR registrant contact block.
            "date_built": pa.array([r.get("date_built") for r in rows], pa.string()),
            "owner_name": pa.array([r.get("owner_name") for r in rows], pa.string()),
            "owner_street": pa.array([r.get("owner_street") for r in rows], pa.string()),
            "owner_city": pa.array([r.get("owner_city") for r in rows], pa.string()),
            "owner_state": pa.array([r.get("owner_state") for r in rows], pa.string()),
            "owner_zip": pa.array([r.get("owner_zip") for r in rows], pa.string()),
            "owner_phone": pa.array([r.get("owner_phone") for r in rows], pa.string()),
            # Columns the slim projection drops:
            "structure_type_desc": pa.array([r.get("desc") for r in rows], pa.string()),
            "carriers": pa.array([r.get("carriers") for r in rows], pa.string()),
        }
    )
    pq.write_table(table, path)


def _reference_union(paths: list[Path]) -> list[tuple]:
    """The per-state union the frontend produces today, computed without
    DuckDB: read each towers.parquet, rename the slim columns to the
    TowerRow aliases, drop coordinate-less rows. Returns hashable row
    tuples for a multiset comparison."""

    def _s(row: dict, key: str) -> str | None:
        return None if row.get(key) is None else str(row[key])

    out: list[tuple] = []
    for p in paths:
        for r in pq.read_table(p).to_pylist():
            if r.get("lat") is None or r.get("lon") is None:
                continue
            owner = _s(r, "parcel_owner")
            out.append(
                (
                    _s(r, "asr_number"),
                    owner,
                    _cid(owner),
                    None if r.get("height_m") is None else float(r["height_m"]),
                    _s(r, "state"),
                    None if r.get("is_active") is None else bool(r["is_active"]),
                    float(r["lat"]),
                    float(r["lon"]),
                    _s(r, "date_built"),
                    _s(r, "owner_name"),
                    _s(r, "owner_street"),
                    _s(r, "owner_city"),
                    _s(r, "owner_state"),
                    _s(r, "owner_zip"),
                    _s(r, "owner_phone"),
                )
            )
    return out


def _row_tuple(t: dict) -> tuple:
    return (
        t["asr"],
        t["owner"],
        t["cid"],
        t["height_m"],
        t["state"],
        t["active"],
        t["lat"],
        t["lon"],
        t["date_built"],
        t["tower_owner"],
        t["tower_owner_street"],
        t["tower_owner_city"],
        t["tower_owner_state"],
        t["tower_owner_zip"],
        t["tower_owner_phone"],
    )


# Two-state fixture: AR (05) + FL (12), with a null owner, a null active
# flag, and a coordinate-less row that must be dropped.
_AR_TOWERS = [
    {
        "asr_number": "080946",
        "parcel_owner": "MITCHELL VICKI",
        "height_m": 79.248,
        "state": "AR",
        "is_active": True,
        "lat": 33.0,
        "lon": -91.3,
        # FCC-sourced row: carries the build date + ASR registrant contact
        # block (v2 fields — the second AR row leaves them null, FAA-style).
        "date_built": "1990-06-14",
        "owner_name": "SBA TOWERS II LLC",
        "owner_street": "8051 CONGRESS AVE",
        "owner_city": "BOCA RATON",
        "owner_state": "FL",
        "owner_zip": "33487",
        "owner_phone": "(561) 995-7670",
        "desc": "LATTICE TOWER",
        "carriers": '["VERIZON"]',
    },
    {
        "asr_number": "080947",
        "parcel_owner": None,  # un-clusterable landowner → '' on the client
        "height_m": 50.0,
        "state": "AR",
        "is_active": True,
        "lat": 34.1,
        "lon": -92.0,
        "desc": "MONOPOLE",
        "carriers": None,
    },
    {
        "asr_number": "080948",  # no coordinates → dropped by the lat/lon filter
        "parcel_owner": "GHOST TOWER LLC",
        "height_m": 60.0,
        "state": "AR",
        "is_active": False,
        "lat": None,
        "lon": -92.5,
        "desc": "GUYED",
        "carriers": None,
    },
]
_FL_TOWERS = [
    {
        "asr_number": "120001",
        "parcel_owner": "WEYERHAEUSER COMPANY",
        "height_m": 120.0,
        "state": "FL",
        "is_active": None,  # unknown status → null, client coerces to false
        "lat": 27.5,
        "lon": -81.2,
        "desc": "LATTICE TOWER",
        "carriers": '["ATT","TMOBILE"]',
    },
]


def _build_two_state_fixture(root: Path) -> list[Path]:
    _make_towers_parquet(root / "05" / "towers.parquet", _AR_TOWERS)
    _make_towers_parquet(root / "12" / "towers.parquet", _FL_TOWERS)
    return [root / "05" / "towers.parquet", root / "12" / "towers.parquet"]


def test_build_writes_schema_versioned_envelope(tmp_path: Path) -> None:
    _build_two_state_fixture(tmp_path)
    result = build_national_towers(composite_root=tmp_path)

    data = json.loads((tmp_path / TOWERS_FILENAME).read_text())
    assert data["schema_version"] == TOWERS_SCHEMA_VERSION
    assert "generated_at" in data
    assert data["states"] == ["05", "12"]
    # One AR tower dropped for missing coordinates → 3 of 4 survive.
    assert data["count"] == 3
    assert data["count"] == len(data["towers"])
    assert result["count"] == 3
    assert result["path"] == str(tmp_path / TOWERS_FILENAME)


def test_every_row_has_exactly_the_towerrow_fields(tmp_path: Path) -> None:
    _build_two_state_fixture(tmp_path)
    build_national_towers(composite_root=tmp_path)

    towers = json.loads((tmp_path / TOWERS_FILENAME).read_text())["towers"]
    assert towers, "expected non-empty towers"
    for t in towers:
        # Exactly the slim TowerRow fields — structure_type_desc/carriers dropped.
        assert set(t.keys()) == ROW_FIELDS


def test_equivalent_to_per_state_union(tmp_path: Path) -> None:
    """The combined file == the per-state union the frontend builds today."""
    paths = _build_two_state_fixture(tmp_path)
    build_national_towers(composite_root=tmp_path)

    towers = json.loads((tmp_path / TOWERS_FILENAME).read_text())["towers"]
    produced = Counter(_row_tuple(t) for t in towers)
    expected = Counter(_reference_union(paths))
    assert produced == expected

    # Not vacuous: the named towers + their derived field values are present.
    by_asr = {t["asr"]: t for t in towers}
    assert by_asr["080946"]["owner"] == "MITCHELL VICKI"
    assert by_asr["080946"]["state"] == "AR"
    assert by_asr["080946"]["lat"] == 33.0 and by_asr["080946"]["lon"] == -91.3
    assert by_asr["080947"]["owner"] is None  # null landowner preserved
    assert by_asr["120001"]["active"] is None  # null status preserved
    assert "080948" not in by_asr  # coordinate-less row dropped

    # Baked cid == the canonical recipe; an un-clusterable owner → ''.
    assert by_asr["080946"]["cid"] == _cid("MITCHELL VICKI")
    assert by_asr["080946"]["cid"] != ""
    assert by_asr["080947"]["cid"] == ""  # null landowner → no Lead key

    # v2: the ASR registrant contact block + build date ride the FCC-style
    # row and stay null on the FAA-style one (audit M-b/M-c).
    assert by_asr["080946"]["tower_owner"] == "SBA TOWERS II LLC"
    assert by_asr["080946"]["tower_owner_phone"] == "(561) 995-7670"
    assert by_asr["080946"]["date_built"] == "1990-06-14"
    assert by_asr["080947"]["tower_owner"] is None
    assert by_asr["080947"]["date_built"] is None


def test_state_without_towers_parquet_is_skipped(tmp_path: Path) -> None:
    _make_towers_parquet(tmp_path / "05" / "towers.parquet", _AR_TOWERS)
    # 12 is "composed" but has no towers.parquet → contributes nothing.
    (tmp_path / "12").mkdir(parents=True, exist_ok=True)
    (tmp_path / "12" / "catalog.json").write_text("{}")

    build_national_towers(composite_root=tmp_path)
    data = json.loads((tmp_path / TOWERS_FILENAME).read_text())
    assert data["states"] == ["05"]
    assert {t["state"] for t in data["towers"]} == {"AR"}


def test_empty_composite_root_writes_empty_file(tmp_path: Path) -> None:
    """No composed states at all → a valid, empty, still-loadable file."""
    result = build_national_towers(composite_root=tmp_path)
    data = json.loads((tmp_path / TOWERS_FILENAME).read_text())
    assert data["schema_version"] == TOWERS_SCHEMA_VERSION
    assert data["towers"] == []
    assert data["count"] == 0
    assert result["count"] == 0
