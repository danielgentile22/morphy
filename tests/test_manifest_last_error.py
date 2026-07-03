"""Manifest schema v3 (#236): structured last_error + tolerant migration.

Covers the fetch-library half of the slice — mark_check_failed /
mark_fetch_failed persist {url, error, elapsed, at}, the puller extracts
the URL tried from the error message (manual_url fallback), and pre-bump
manifests still load.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fetch import manifest as manifest_mod
from fetch import storage as storage_mod
from fetch.legal import AutomationPolicy, CommercialUse, LegalInfo
from fetch.manifest import Manifest
from fetch.puller import check_one, fetch_one

MANUAL_URL = "https://example.com/manual-landing"


@pytest.fixture(autouse=True)
def _no_fetch_log(monkeypatch):
    monkeypatch.setattr("fetch.puller.log_event", lambda *a, **k: None)


@dataclass
class _Source:
    """Duck-typed DataSource — just what check_one / fetch_one read."""

    id: str = "src"
    name: str = "Src"
    update_cadence_days: int | None = 30
    check_error: str | None = None
    fetch_error: str | None = None
    legal: LegalInfo = field(
        default_factory=lambda: LegalInfo(
            publisher="x",
            license="x",
            license_url="x",
            automation=AutomationPolicy.ALLOWED,
            commercial_use=CommercialUse.ALLOWED,
            manual_url=MANUAL_URL,
        )
    )

    def credentials_available(self) -> bool:
        return True

    def remote_version(self) -> str:
        if self.check_error:
            raise RuntimeError(self.check_error)
        return "v1"

    def fetch(self, dest_dir: Path, progress):
        raise RuntimeError(self.fetch_error)


# ── migration: pre-v3 manifests still load ──────────────────────────────


def _v2_entry() -> dict:
    return {
        "remote_version": "v1",
        "local_version": "v1",
        "fetched_at": "2026-01-01T00:00:00+00:00",
        "checked_at": "2026-01-01T00:00:00+00:00",
        "bytes": 10,
        "files": ["a.zip"],
        "status": "ok",
        "error": None,
        "update_cadence_days": 30,
        "next_recommended_check_at": "2026-01-31T00:00:00+00:00",
    }


def test_v2_manifest_loads_and_resaves_as_v3(monkeypatch, tmp_path):
    path = tmp_path / "manifest.json"
    monkeypatch.setattr(manifest_mod, "MANIFEST_PATH", path)
    path.write_text(
        json.dumps({"schema_version": 2, "last_full_check": None, "sources": {"src": _v2_entry()}})
    )

    m = Manifest.load()
    assert m.sources["src"].last_error is None
    assert m.sources["src"].is_installed()

    m.save()
    raw = json.loads(path.read_text())
    assert raw["schema_version"] == 3
    assert raw["sources"]["src"]["last_error"] is None


def test_v1_manifest_still_loads(monkeypatch, tmp_path):
    """v1 entries lack cadence fields AND last_error — defaults cover both."""
    path = tmp_path / "manifest.json"
    monkeypatch.setattr(manifest_mod, "MANIFEST_PATH", path)
    v1_entry = {k: v for k, v in _v2_entry().items() if not k.startswith(("update_", "next_"))}
    path.write_text(json.dumps({"schema_version": 1, "sources": {"src": v1_entry}}))

    m = Manifest.load()
    e = m.sources["src"]
    assert e.last_error is None
    assert e.update_cadence_days is None
    assert e.is_installed()


def test_v3_last_error_round_trips(monkeypatch, tmp_path):
    path = tmp_path / "manifest.json"
    monkeypatch.setattr(manifest_mod, "MANIFEST_PATH", path)
    m = Manifest()
    m.mark_fetch_failed("src", "HttpError: boom", url="https://ex.com/f.zip", elapsed=1.5)
    m.save()

    reloaded = Manifest.load()
    le = reloaded.sources["src"].last_error
    assert le["url"] == "https://ex.com/f.zip"
    assert le["error"] == "HttpError: boom"
    assert le["elapsed"] == 1.5
    assert le["at"]


# ── mark_* record the structured detail ──────────────────────────────────


def test_mark_check_failed_records_last_error():
    m = Manifest()
    m.mark_check_failed("src", "HttpError: 500", url="https://ex.com/v", elapsed=0.3)
    e = m.entry("src")
    assert e.status == "check_failed"
    assert e.last_error == {
        "url": "https://ex.com/v",
        "error": "HttpError: 500",
        "elapsed": 0.3,
        "at": e.checked_at,
    }


# ── puller records url + elapsed ─────────────────────────────────────────


def test_check_one_failure_extracts_url_from_message():
    src = _Source(check_error="HEAD https://data.example.gov/f.zip → HTTP 500")
    m = Manifest()
    out = check_one(src, m)
    assert out.ok is False
    le = m.entry("src").last_error
    assert le["url"] == "https://data.example.gov/f.zip"
    assert "HTTP 500" in le["error"]
    assert isinstance(le["elapsed"], float)
    assert le["at"]


def test_fetch_one_failure_falls_back_to_manual_url(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    src = _Source(fetch_error="disk full, no url in this message")
    m = Manifest()
    out = fetch_one(src, m, progress=lambda *_a: None)
    assert out.ok is False
    le = m.entry("src").last_error
    assert le["url"] == MANUAL_URL
    assert "disk full" in le["error"]
