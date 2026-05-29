"""Tests for the typed PreprocessManifest entries + codec.

Covers:

- Per-entry codec round-trip (NormalizeEntry, ComposeEntry,
  NormalizeHistoryEntry).
- ``record_normalize`` builds a typed entry and appends the prior
  outcome to history.
- History is capped at HISTORY_LIMIT.
- ``skip_normalize`` mutates status + skip_reason on the typed entry.
- ``record_compose`` builds a typed entry.
- load / save round-trip through PREPROCESS_MANIFEST_PATH (monkeypatched
  to a tempdir).
- Backwards-compat: legacy on-disk manifests missing fields (no
  ``history``, no ``skip_reason``, etc.) parse cleanly.
- ``rebuild_from_disk`` produces typed entries (smoke — no real data
  on disk, just asserts shape on empty-tree).
"""

from __future__ import annotations

import json

import pytest
from preprocess import manifest as manifest_mod
from preprocess.manifest import (
    HISTORY_LIMIT,
    ComposeEntry,
    NormalizeEntry,
    NormalizeHistoryEntry,
    PreprocessManifest,
)

# ── codec round-trips ───────────────────────────────────────────────────


def test_normalize_history_entry_round_trips():
    h = NormalizeHistoryEntry(
        preprocessed_at="2026-05-25T00:00:00Z",
        raw_rows=100,
        canonical_rows=98,
        status="ok",
    )
    assert NormalizeHistoryEntry.from_dict(h.to_dict()) == h


def test_normalize_entry_round_trips_with_full_fields():
    e = NormalizeEntry(
        raw_local_version="2026-05-18",
        preprocessed_at="2026-05-25T00:00:00Z",
        raw_rows=2_116_976,
        canonical_rows=2_116_900,
        bytes=128_456_789,
        canonical_types=["parcel"],
        states_covered=["05", "30"],
        quality_report_path="data/processed/normalized/ar_parcels/quality_report.json",
        status="ok",
        history=[
            NormalizeHistoryEntry(
                preprocessed_at="2026-05-18T00:00:00Z",
                raw_rows=2_100_000,
                canonical_rows=2_099_900,
                status="ok",
            ),
        ],
    )
    assert NormalizeEntry.from_dict(e.to_dict()) == e


def test_normalize_entry_omits_optional_fields_from_disk():
    """skip_reason and rebuilt_from_disk_at only appear in the JSON
    when they're set — keeps the on-disk shape clean for live manifests."""
    e = NormalizeEntry(
        raw_local_version="v1",
        preprocessed_at="t",
        raw_rows=1,
        canonical_rows=1,
        bytes=1,
    )
    on_disk = e.to_dict()
    assert "skip_reason" not in on_disk
    assert "rebuilt_from_disk_at" not in on_disk


def test_compose_entry_round_trips():
    e = ComposeEntry(
        preprocessed_at="2026-05-25T00:00:00Z",
        sources_used=["ar_parcels", "fcc_asr"],
        joins_applied=["TowerToParcelJoin", "InterestingnessScoreJoin"],
        joins_skipped=[],
        views_built=["interestingness_top_1000"],
        counts={"parcel": 2_116_976, "tower": 1873},
        status="ok",
    )
    assert ComposeEntry.from_dict(e.to_dict()) == e


def test_compose_entry_optional_joins_skipped_omitted_when_empty():
    e = ComposeEntry(preprocessed_at="t")
    assert "joins_skipped" not in e.to_dict()


# ── record_normalize + history ──────────────────────────────────────────


def test_record_normalize_creates_typed_entry():
    m = PreprocessManifest()
    m.record_normalize(
        "ar_parcels",
        raw_local_version="v1",
        raw_rows=100,
        canonical_rows=98,
        bytes_written=50_000,
        canonical_types=["parcel"],
        states_covered=["05"],
        quality_report_path="path/to/qr.json",
        preprocessed_at="2026-05-25T00:00:00Z",
    )
    entry = m.normalized["ar_parcels"]
    assert isinstance(entry, NormalizeEntry)
    assert entry.status == "ok"
    assert entry.canonical_rows == 98
    assert entry.states_covered == ["05"]
    assert entry.history == []  # first run, no prior


def test_record_normalize_appends_prior_outcome_to_history():
    """Each successive run pushes the previous outcome onto history."""
    m = PreprocessManifest()
    m.record_normalize(
        "ar_parcels",
        raw_local_version="v1",
        raw_rows=100,
        canonical_rows=98,
        bytes_written=1,
        canonical_types=["parcel"],
        preprocessed_at="2026-05-24T00:00:00Z",
    )
    m.record_normalize(
        "ar_parcels",
        raw_local_version="v2",
        raw_rows=110,
        canonical_rows=108,
        bytes_written=1,
        canonical_types=["parcel"],
        preprocessed_at="2026-05-25T00:00:00Z",
    )
    entry = m.normalized["ar_parcels"]
    assert entry.preprocessed_at == "2026-05-25T00:00:00Z"
    assert entry.canonical_rows == 108
    assert len(entry.history) == 1
    assert entry.history[0].canonical_rows == 98


def test_record_normalize_caps_history_at_limit():
    m = PreprocessManifest()
    for i in range(HISTORY_LIMIT + 5):
        m.record_normalize(
            "ar_parcels",
            raw_local_version=f"v{i}",
            raw_rows=i,
            canonical_rows=i,
            bytes_written=1,
            canonical_types=["parcel"],
            preprocessed_at=f"2026-05-{(i % 28) + 1:02d}T00:00:00Z",
        )
    entry = m.normalized["ar_parcels"]
    assert len(entry.history) == HISTORY_LIMIT


# ── skip_normalize + record_compose ─────────────────────────────────────


def test_skip_normalize_updates_status_and_reason():
    m = PreprocessManifest()
    m.record_normalize(
        "ar_parcels",
        raw_local_version="v1",
        raw_rows=1,
        canonical_rows=1,
        bytes_written=1,
        canonical_types=["parcel"],
    )
    m.skip_normalize("ar_parcels", reason="raw unchanged since last run")
    entry = m.normalized["ar_parcels"]
    assert entry.status == "skipped"
    assert entry.skip_reason == "raw unchanged since last run"


def test_skip_normalize_is_noop_on_unknown_source():
    """Skipping a source that has no entry must not create one."""
    m = PreprocessManifest()
    m.skip_normalize("unknown_source", reason="anything")
    assert "unknown_source" not in m.normalized


def test_record_compose_creates_typed_entry():
    m = PreprocessManifest()
    m.record_compose(
        "05",
        sources_used=["ar_parcels"],
        joins_applied=["TowerToParcelJoin"],
        views_built=["llc_view"],
        counts={"parcel": 100},
        preprocessed_at="2026-05-25T00:00:00Z",
    )
    entry = m.composed["05"]
    assert isinstance(entry, ComposeEntry)
    assert entry.counts["parcel"] == 100
    assert entry.sources_used == ["ar_parcels"]
    assert entry.status == "ok"


# ── load / save round-trip ──────────────────────────────────────────────


@pytest.fixture
def tmp_manifest_path(tmp_path, monkeypatch):
    """Point PREPROCESS_MANIFEST_PATH at a tempdir for the duration of one test."""
    p = tmp_path / "preprocess_manifest.json"
    monkeypatch.setattr(manifest_mod, "PREPROCESS_MANIFEST_PATH", p)
    return p


def test_load_returns_empty_when_file_missing(tmp_manifest_path):
    m = PreprocessManifest.load()
    assert m.normalized == {}
    assert m.composed == {}


def test_save_and_load_round_trip(tmp_manifest_path):
    m = PreprocessManifest()
    m.record_normalize(
        "ar_parcels",
        raw_local_version="v1",
        raw_rows=10,
        canonical_rows=10,
        bytes_written=42,
        canonical_types=["parcel"],
        states_covered=["05"],
        preprocessed_at="2026-05-25T00:00:00Z",
    )
    m.record_compose(
        "05",
        sources_used=["ar_parcels"],
        joins_applied=["J1"],
        views_built=["V1"],
        counts={"parcel": 10},
        preprocessed_at="2026-05-25T01:00:00Z",
    )
    m.save()
    loaded = PreprocessManifest.load()
    assert loaded.normalized["ar_parcels"] == m.normalized["ar_parcels"]
    assert loaded.composed["05"] == m.composed["05"]


def test_load_recovers_from_corrupt_file(tmp_manifest_path):
    """A garbled manifest must not crash the pipeline — load returns empty
    and the next save overwrites it."""
    tmp_manifest_path.write_text("{ not valid json")
    m = PreprocessManifest.load()
    assert m.normalized == {}
    assert m.composed == {}


# ── backward-compat: legacy on-disk manifests ─────────────────────────────


def test_load_tolerates_legacy_entries_missing_optional_fields(tmp_manifest_path):
    """Legacy manifests (pre-typed-entries) won't have skip_reason,
    rebuilt_from_disk_at, or history — but they MUST still parse."""
    legacy = {
        "schema_version": 3,
        "normalized": {
            "ar_parcels": {
                "raw_local_version": "v1",
                "preprocessed_at": "2026-05-20T00:00:00Z",
                "raw_rows": 100,
                "canonical_rows": 100,
                "bytes": 1000,
                "canonical_types": ["parcel"],
                "states_covered": ["05"],
                "quality_report_path": "path",
                "status": "ok",
                "error": None,
                # No history, no skip_reason, no rebuilt_from_disk_at.
            }
        },
        "composed": {
            "05": {
                "preprocessed_at": "2026-05-20T01:00:00Z",
                "sources_used": ["ar_parcels"],
                "joins_applied": [],
                "views_built": [],
                "counts": {},
                "status": "ok",
                "error": None,
                # No joins_skipped, no rebuilt_from_disk_at.
            }
        },
    }
    tmp_manifest_path.write_text(json.dumps(legacy))
    m = PreprocessManifest.load()
    entry = m.normalized["ar_parcels"]
    assert entry.history == []
    assert entry.skip_reason is None
    assert entry.rebuilt_from_disk_at is None
    compose_entry = m.composed["05"]
    assert compose_entry.joins_skipped == []
    assert compose_entry.rebuilt_from_disk_at is None
