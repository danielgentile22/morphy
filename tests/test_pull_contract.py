"""The puller owns the pull contract (#264).

Two orchestration contracts moved out of the source adapters:
  1. remote_version is captured once, by the puller, before the download —
     unless the source derives it as a byproduct of fetch.
  2. one manifest install-stamp owns the freshness clock + file-list/bytes
     derivation, so the auto-fetch and manual-install paths produce
     identical entries for identical current/ contents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fetch import storage as storage_mod
from fetch.base import CATEGORY_PARCELS, DataSource, FetchResult
from fetch.install import mark_manual_install
from fetch.legal import AutomationPolicy, CommercialUse, LegalInfo
from fetch.manifest import Manifest
from fetch.puller import fetch_one


def _legal() -> LegalInfo:
    return LegalInfo(
        publisher="x",
        license="public domain",
        license_url="https://example.com",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED,
        manual_url="https://example.com/manual",
    )


@dataclass
class _CountingSource(DataSource):
    """Writes one file; counts remote_version() calls; optionally derives
    its version during fetch instead of exposing it to the pre-probe."""

    derive: bool = False
    probe_calls: int = 0
    fetch_version: str | None = None

    def __post_init__(self):
        self.id = "counting_src"
        self.name = "counting"
        self.category = CATEGORY_PARCELS
        self.coverage = "test"
        self.cadence = "Annual"
        self.description = "counts probes"
        self.legal = _legal()
        self.estimated_size_mb = 0.01
        self.update_cadence_days = 30
        self.derives_version_on_fetch = self.derive

    def remote_version(self) -> str:
        self.probe_calls += 1
        return "probe-v1"

    def fetch(self, dest_dir: Path, progress) -> FetchResult:
        (dest_dir / "data.bin").write_bytes(b"y" * 2048)
        progress(1, 1, "data.bin")
        return FetchResult(
            files=[dest_dir / "data.bin"], total_bytes=2048, remote_version=self.fetch_version
        )


def _manifest(monkeypatch, tmp_path) -> Manifest:
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    import fetch.manifest as manifest_mod

    monkeypatch.setattr(manifest_mod, "MANIFEST_PATH", tmp_path / "manifest.json")
    return Manifest.load()


def test_puller_probes_version_once_before_download(monkeypatch, tmp_path):
    m = _manifest(monkeypatch, tmp_path)
    src = _CountingSource(derive=False)
    out = fetch_one(src, m, progress=lambda *_a: None)
    assert out.ok is True
    assert src.probe_calls == 1  # one probe per pull, from the puller
    assert out.remote_version == "probe-v1"
    assert m.entry(src.id).local_version == "probe-v1"


def test_derived_source_is_not_pre_probed(monkeypatch, tmp_path):
    m = _manifest(monkeypatch, tmp_path)
    src = _CountingSource(derive=True, fetch_version="fetch-v9")
    out = fetch_one(src, m, progress=lambda *_a: None)
    assert out.ok is True
    assert src.probe_calls == 0  # puller trusts the fetch-derived version
    assert out.remote_version == "fetch-v9"
    assert m.entry(src.id).remote_version == "fetch-v9"


def test_auto_and_manual_stamp_produce_identical_derived_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)

    # Identical current/ contents for two source ids.
    for sid in ("auto_src", "manual_src"):
        cur = storage_mod.current_dir(sid)
        cur.mkdir(parents=True, exist_ok=True)
        (cur / "a.csv").write_bytes(b"12345")
        (cur / "sub").mkdir(exist_ok=True)
        (cur / "sub" / "b.csv").write_bytes(b"6789")

    m = Manifest()
    m.stamp_installed("auto_src", local_version="v1", remote_version="v1", cadence_days=30)

    @dataclass
    class _Src:
        id: str = "manual_src"
        update_cadence_days: int | None = 30

    mark_manual_install(_Src(), m)

    a = m.entry("auto_src")
    b = m.entry("manual_src")
    # The derived fields are identical for identical contents + cadence.
    assert a.bytes == b.bytes == 9
    assert sorted(Path(f).name for f in a.files) == sorted(Path(f).name for f in b.files)
    assert a.status == b.status == "ok"
    assert a.update_cadence_days == b.update_cadence_days == 30
    assert (a.next_recommended_check_at is not None) and (b.next_recommended_check_at is not None)
    # Only the version identity legitimately differs.
    assert a.local_version == "v1"
    assert b.local_version == "manual"


def test_freshness_clock_has_one_owner(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    cur = storage_mod.current_dir("s")
    cur.mkdir(parents=True, exist_ok=True)
    (cur / "f").write_bytes(b"x")

    from datetime import datetime, timedelta

    import fetch.manifest as manifest_mod

    m = Manifest()
    m.stamp_installed("s", local_version="v", remote_version="v", cadence_days=30)
    nra = datetime.fromisoformat(m.entry("s").next_recommended_check_at)
    fetched = datetime.fromisoformat(m.entry("s").fetched_at)
    assert nra - fetched == timedelta(days=30)
    # Cadence-resync recomputes it from the same helper (fetched_at + cadence).
    m.update_cadence("s", 7)
    nra7 = datetime.fromisoformat(m.entry("s").next_recommended_check_at)
    assert nra7 - fetched == timedelta(days=7)
    assert manifest_mod._next_check_iso(fetched, None) is None


@dataclass
class _NoCadence(DataSource):
    def __post_init__(self):
        self.id = "no_cadence"
        self.name = "n"
        self.category = CATEGORY_PARCELS
        self.coverage = "test"
        self.cadence = "Static"
        self.description = "one-shot"
        self.legal = _legal()
        self.estimated_size_mb = 0.01
        self.update_cadence_days = None

    def remote_version(self) -> str:
        return "static"

    def fetch(self, dest_dir: Path, progress) -> FetchResult:
        (dest_dir / "one.bin").write_bytes(b"z" * 100)
        return FetchResult(files=[dest_dir / "one.bin"], total_bytes=100)


def test_no_cadence_leaves_no_scheduled_recheck(monkeypatch, tmp_path):
    m = _manifest(monkeypatch, tmp_path)
    out = fetch_one(_NoCadence(), m, progress=lambda *_a: None)
    assert out.ok is True
    assert m.entry("no_cadence").next_recommended_check_at is None
