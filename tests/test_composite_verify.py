"""Composite verify (#239): fixture composites diffed against a deploy receipt.

The acceptance matrix from the issue: all-pass, count-drop-beyond-threshold
fails, schema mismatch fails, missing inventory fails, no-receipt-yet
reports without blocking.
"""

from __future__ import annotations

import json
from pathlib import Path

from data_tui.verify import load_receipt, snapshot, verify, write_receipt


def _index(parcel: int = 1000, tower: int = 100) -> dict:
    return {
        "schema_version": 1,
        "states": [
            {
                "fips": "54",
                "abbr": "WV",
                "name": "West Virginia",
                "counts": {"parcel": parcel, "tower": tower},
            }
        ],
    }


def _owners(schema_version: int = 5, count: int = 500) -> dict:
    return {
        "schema_version": schema_version,
        "count": count,
        "generated_at": "2026-07-01T00:00:00+00:00",
        "owners": [],
    }


def _composite(tmp_path: Path, parcel=1000, tower=100, schema=5, owners=500) -> Path:
    root = tmp_path / "composite"
    state = root / "54"
    state.mkdir(parents=True, exist_ok=True)
    (root / "index.json").write_text(json.dumps(_index(parcel, tower)))
    (root / "owners_index.json").write_text(json.dumps(_owners(schema, owners)))
    (state / "towers.parquet").write_bytes(b"t")
    (state / "parcels.pmtiles").write_bytes(b"p")
    # Compose-input dir the sync contract excludes — must never enter inventory.
    (state / "parcels").mkdir(exist_ok=True)
    (state / "parcels" / "county1.geojson").write_bytes(b"c")
    return root


def _find(report, name):
    return next(c for c in report.checks if c.name == name)


def test_snapshot_inventory_follows_sync_contract(tmp_path):
    snap = snapshot(_composite(tmp_path))
    assert "54/towers.parquet" in snap["inventory"]
    assert "54/parcels.pmtiles" in snap["inventory"]
    assert not any("county1" in f for f in snap["inventory"])
    assert snap["state_counts"] == {"54": {"parcel": 1000, "tower": 100}}
    assert snap["owners"]["schema_version"] == 5


def test_no_receipt_reports_without_blocking(tmp_path):
    report = verify(_composite(tmp_path), None)
    assert report.passed
    assert not report.blocks_deploy
    assert report.baseline_at is None
    assert "no deploy receipt yet" in _find(report, "baseline").detail


def test_all_pass_against_matching_receipt(tmp_path):
    comp = _composite(tmp_path)
    receipt = write_receipt(snapshot(comp), tmp_path / "receipt.json")
    report = verify(comp, receipt)
    assert report.passed
    assert not report.blocks_deploy
    assert report.baseline_at == receipt["deployed_at"]


def test_count_drop_beyond_threshold_fails(tmp_path):
    comp = _composite(tmp_path)
    receipt = write_receipt(snapshot(comp), tmp_path / "receipt.json")
    (comp / "index.json").write_text(json.dumps(_index(parcel=800)))  # -20%
    report = verify(comp, receipt)
    assert report.blocks_deploy
    bad = _find(report, "counts:54:parcel")
    assert not bad.ok
    assert "1,000 → 800" in bad.detail
    assert _find(report, "counts:54:tower").ok  # unchanged count still passes


def test_count_drop_within_threshold_passes(tmp_path):
    comp = _composite(tmp_path)
    receipt = write_receipt(snapshot(comp), tmp_path / "receipt.json")
    (comp / "index.json").write_text(json.dumps(_index(parcel=950)))  # -5%
    assert verify(comp, receipt).passed


def test_owners_schema_mismatch_fails(tmp_path):
    comp = _composite(tmp_path)
    receipt = write_receipt(snapshot(comp), tmp_path / "receipt.json")
    (comp / "owners_index.json").write_text(json.dumps(_owners(schema_version=6)))
    report = verify(comp, receipt)
    assert report.blocks_deploy
    assert "v5 → v6" in _find(report, "owners:schema").detail
    assert _find(report, "owners:count").ok


def test_owners_count_drop_fails(tmp_path):
    comp = _composite(tmp_path)
    receipt = write_receipt(snapshot(comp), tmp_path / "receipt.json")
    (comp / "owners_index.json").write_text(json.dumps(_owners(count=100)))
    report = verify(comp, receipt)
    assert not _find(report, "owners:count").ok


def test_missing_inventory_fails(tmp_path):
    comp = _composite(tmp_path)
    receipt = write_receipt(snapshot(comp), tmp_path / "receipt.json")
    (comp / "54" / "towers.parquet").unlink()
    report = verify(comp, receipt)
    assert report.blocks_deploy
    bad = _find(report, "inventory")
    assert "54/towers.parquet" in bad.detail


def test_state_missing_from_fresh_composite_fails(tmp_path):
    comp = _composite(tmp_path)
    receipt = write_receipt(snapshot(comp), tmp_path / "receipt.json")
    (comp / "index.json").write_text(json.dumps({"schema_version": 1, "states": []}))
    report = verify(comp, receipt)
    assert not _find(report, "counts:54").ok


def test_unreadable_composite_fails_closed(tmp_path):
    report = verify(tmp_path / "nowhere", None)
    assert report.blocks_deploy
    assert not report.checks[0].ok


def test_receipt_round_trips(tmp_path):
    comp = _composite(tmp_path)
    path = tmp_path / "receipt.json"
    written = write_receipt(snapshot(comp), path)
    assert load_receipt(path) == written
    assert written["schema_version"] == 1
    assert written["deployed_at"]


def test_load_receipt_missing_or_corrupt_is_none(tmp_path):
    assert load_receipt(tmp_path / "absent.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert load_receipt(bad) is None
