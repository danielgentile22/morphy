"""Tests for the puller's resumable-partial path (Slice F).

The bug: ``prepare_fresh_partial`` wipes ``.partial/`` at the start of
every fetch, so a stalled NC OneMap fetch (1,186 pages, ~1 hr) had to
restart from page 1 instead of skipping already-complete page files.

The fix:
  - ``DataSource.supports_resume`` opt-in flag (default False).
  - ``prepare_partial_for_resume`` storage helper that creates the dir
    without wiping.
  - ``puller.fetch_one`` dispatches based on the flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from fetch import storage as storage_mod
from fetch.base import (
    CATEGORY_PARCELS,
    DataSource,
    FetchResult,
)
from fetch.legal import AutomationPolicy, CommercialUse, LegalInfo
from fetch.manifest import Manifest
from fetch.puller import fetch_one
from fetch.sources.nc_onemap_parcels import NcOnemapParcels
from fetch.storage import (
    prepare_fresh_partial,
    prepare_partial_for_resume,
)


# ── storage helpers ──────────────────────────────────────────────────────


def test_prepare_fresh_partial_wipes_existing_files(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    sid = "test_src"
    p = prepare_fresh_partial(sid)
    leftover = p / "page_0001.geojson"
    leftover.write_bytes(b"x" * 4096)
    assert leftover.exists()

    p2 = prepare_fresh_partial(sid)
    assert p2 == p
    assert not leftover.exists(), "prepare_fresh_partial should wipe pre-existing files"


def test_prepare_partial_for_resume_preserves_existing_files(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    sid = "test_src"
    p = prepare_partial_for_resume(sid)
    page = p / "page_0042.geojson"
    page.write_bytes(b"x" * 4096)
    assert page.exists()

    p2 = prepare_partial_for_resume(sid)
    assert p2 == p
    assert page.exists(), "resume mode must preserve pre-existing per-page files"
    assert page.stat().st_size == 4096


def test_nc_onemap_declares_supports_resume():
    """The one production source where resumability is load-bearing."""
    src = NcOnemapParcels()
    assert src.supports_resume is True


def test_default_source_does_not_support_resume():
    """Resume is opt-in — single-file fetches must keep the wipe behaviour."""
    from fetch.sources.uspvdb import SOURCE as USPVDB

    assert getattr(USPVDB, "supports_resume", False) is False


# ── fetch_one dispatch ────────────────────────────────────────────────────


@dataclass
class _StubSource(DataSource):
    """Minimal source for exercising the puller dispatch in tests."""

    pages_to_make: int = 3
    supports_resume_flag: bool = False
    fetch_calls: int = 0

    def __post_init__(self):
        self.id = "stub_src"
        self.name = "stub"
        self.category = CATEGORY_PARCELS
        self.coverage = "test"
        self.cadence = "Annual"
        self.description = "stub"
        self.legal = LegalInfo(
            publisher="stub",
            license="public domain",
            license_url="https://example.com",
            automation=AutomationPolicy.ALLOWED,
            commercial_use=CommercialUse.ALLOWED_WITH_ATTRIBUTION,
            manual_url="https://example.com/manual",
        )
        self.estimated_size_mb = 0.01
        self.update_cadence_days = None
        self.supports_resume = self.supports_resume_flag

    def remote_version(self) -> str:
        return "v1"

    def fetch(self, dest_dir: Path, progress) -> FetchResult:
        self.fetch_calls += 1
        files = []
        # Honour pre-existing files (resume behaviour) so the test asserts
        # what the real NC OneMap source does.
        for i in range(self.pages_to_make):
            p = dest_dir / f"page_{i:04d}.geojson"
            if not p.exists():
                p.write_bytes(b"x" * 4096)
            files.append(p)
        progress(self.pages_to_make, self.pages_to_make, "done")
        return FetchResult(files=files, remote_version="v1", total_bytes=4096 * len(files))


def _make_manifest(monkeypatch, tmp_path) -> Manifest:
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    # Manifest writes go through MANIFEST_PATH; redirect.
    import scripts.fetch.manifest as manifest_mod

    monkeypatch.setattr(manifest_mod, "MANIFEST_PATH", tmp_path / "manifest.json")
    return Manifest.load()


def test_non_resumable_source_wipes_partial_each_run(monkeypatch, tmp_path):
    """Default behaviour: every fetch starts clean."""
    manifest = _make_manifest(monkeypatch, tmp_path)
    src = _StubSource(pages_to_make=2, supports_resume_flag=False)

    # First fetch — promotes partial to current.
    out1 = fetch_one(src, manifest, progress=lambda *_a, **_kw: None)
    assert out1.ok is True
    # Pre-seed .partial with a stale leftover from a "previous" failed run.
    partial = storage_mod.partial_dir(src.id)
    partial.mkdir(parents=True, exist_ok=True)
    leftover = partial / "stale_leftover.geojson"
    leftover.write_bytes(b"x" * 4096)
    assert leftover.exists()

    # Second fetch — non-resumable, the leftover must be wiped.
    fetch_one(src, manifest, progress=lambda *_a, **_kw: None)
    # promote_partial moves partial → current; the leftover would have
    # surfaced in current/ if it had been preserved.
    cur = storage_mod.current_dir(src.id)
    assert not (cur / "stale_leftover.geojson").exists()


def test_resumable_source_preserves_partial_across_runs(monkeypatch, tmp_path):
    """With supports_resume=True, prior partial contents flow into the
    new fetch, then promote to current."""
    manifest = _make_manifest(monkeypatch, tmp_path)
    src = _StubSource(pages_to_make=3, supports_resume_flag=True)

    # Seed `.partial/` with a page that simulates a previous incomplete run.
    partial = storage_mod.partial_dir(src.id)
    partial.mkdir(parents=True, exist_ok=True)
    pre_existing = partial / "page_0000.geojson"
    pre_existing.write_bytes(b"x" * 4096)

    out = fetch_one(src, manifest, progress=lambda *_a, **_kw: None)
    assert out.ok is True
    # The pre-existing page should have been preserved and promoted.
    cur = storage_mod.current_dir(src.id)
    assert (cur / "page_0000.geojson").exists()
    assert (cur / "page_0001.geojson").exists()
    assert (cur / "page_0002.geojson").exists()
