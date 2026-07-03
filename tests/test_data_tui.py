"""Data TUI slice 1 (#234): badge logic, attention ranking, pilot tests.

The pure freshness/attention matrix is exercised directly; the app itself
is driven through Textual's pilot (headless) — the repo's first UI tests.
Pilot tests wrap their async body in ``asyncio.run`` so no async test
plugin is needed (PRD #233: Textual is the one new dependency).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from data_tui.app import DataTuiApp
from data_tui.freshness import (
    SEV_DEAD,
    SEV_MISSING,
    SEV_STALE,
    attention_items,
    badge_for,
)
from fetch.legal import AutomationPolicy, CommercialUse, LegalInfo
from fetch.manifest import Manifest, SourceEntry
from textual.widgets import DataTable


@pytest.fixture(autouse=True)
def _no_fetch_log(monkeypatch):
    """Keep test sweeps out of the real data/fetch.log."""
    monkeypatch.setattr("fetch.puller.log_event", lambda *a, **k: None)


def _legal(automation: AutomationPolicy) -> LegalInfo:
    return LegalInfo(
        publisher="x",
        license="x",
        license_url="x",
        automation=automation,
        commercial_use=CommercialUse.ALLOWED,
        manual_url="https://example.com",
    )


@dataclass
class FakeSource:
    """Duck-typed DataSource — just what badges, attention, and check_one read."""

    id: str = "fake"
    name: str = "Fake"
    category: str = "Towers"
    coverage: str = "National"
    update_cadence_days: int | None = 30
    legal: LegalInfo = field(default_factory=lambda: _legal(AutomationPolicy.ALLOWED))
    remote: str = "v1"

    @property
    def is_manual_only(self) -> bool:
        return self.legal.automation == AutomationPolicy.MANUAL_ONLY

    @property
    def needs_credentials(self) -> bool:
        return self.legal.automation == AutomationPolicy.CREDENTIALED

    def credentials_available(self) -> bool:
        return True

    def remote_version(self) -> str:
        return self.remote

    def manual_walkthrough(self):
        return None


def _entry(**kw) -> SourceEntry:
    e = SourceEntry()
    for k, v in kw.items():
        setattr(e, k, v)
    return e


def _fresh_entry(version: str = "v1", cadence: int = 30) -> SourceEntry:
    now = datetime.now(UTC)
    return _entry(
        local_version=version,
        remote_version=version,
        status="ok",
        fetched_at=now.isoformat(timespec="seconds"),
        update_cadence_days=cadence,
        next_recommended_check_at=(now + timedelta(days=cadence)).isoformat(timespec="seconds"),
    )


def _past_cadence_entry(cadence: int = 7) -> SourceEntry:
    now = datetime.now(UTC)
    return _entry(
        local_version="v1",
        remote_version="v1",
        status="ok",
        fetched_at=(now - timedelta(days=30)).isoformat(timespec="seconds"),
        update_cadence_days=cadence,
        next_recommended_check_at=(now - timedelta(days=23)).isoformat(timespec="seconds"),
    )


def _manifest(entries: dict[str, SourceEntry]) -> Manifest:
    m = Manifest()
    m.sources = entries
    return m


# ── badge_for ────────────────────────────────────────────────────────────


def test_badge_fresh():
    b = badge_for(FakeSource(), _fresh_entry())
    assert b.kind == "fresh"


def test_badge_stale_past_cadence():
    b = badge_for(FakeSource(update_cadence_days=7), _past_cadence_entry())
    assert b.kind == "stale"
    assert "STALE" in b.label


def test_badge_stale_new_version():
    e = _entry(local_version="v1", remote_version="v2", status="ok")
    b = badge_for(FakeSource(), e)
    assert b.kind == "stale"
    assert "new version" in b.label


def test_badge_missing():
    assert badge_for(FakeSource(), _entry()).kind == "missing"


def test_badge_manual_not_installed():
    s = FakeSource(legal=_legal(AutomationPolicy.MANUAL_ONLY))
    assert badge_for(s, _entry()).kind == "manual"


def test_badge_manual_installed_falls_through_to_freshness():
    s = FakeSource(legal=_legal(AutomationPolicy.MANUAL_ONLY))
    assert badge_for(s, _fresh_entry(version="manual")).kind == "fresh"


def test_badge_dead_on_check_failed():
    assert badge_for(FakeSource(), _entry(status="check_failed")).kind == "dead"


def test_badge_deferred_wins_over_everything():
    assert badge_for(FakeSource(), _entry(status="check_failed"), deferred=True).kind == "deferred"


def test_badge_fresh_when_installed_without_cadence():
    """One-shot reference data (no cadence) reads as fresh, not stale."""
    e = _fresh_entry()
    e.update_cadence_days = None
    b = badge_for(FakeSource(update_cadence_days=None), e)
    assert b.kind == "fresh"


# ── attention_items ──────────────────────────────────────────────────────


def test_attention_ranks_dead_then_missing_then_stale():
    dead = FakeSource(id="a_dead", name="Zed dead")
    missing = FakeSource(id="b_missing", name="Alpha missing")
    stale = FakeSource(id="c_stale", name="Beta stale")
    m = _manifest(
        {
            "a_dead": _entry(status="check_failed", error="500"),
            "b_missing": _entry(),
            "c_stale": _entry(local_version="v1", remote_version="v2", status="ok"),
        }
    )
    items = attention_items([stale, missing, dead], m)
    assert [it.severity for it in items] == [SEV_DEAD, SEV_MISSING, SEV_STALE]
    assert items[0].source_id == "a_dead"


def test_attention_empty_when_all_fresh():
    s = FakeSource()
    assert attention_items([s], _manifest({s.id: _fresh_entry()})) == []


# ── pilot tests ──────────────────────────────────────────────────────────


def _status_cell(app: DataTuiApp, source_id: str) -> str:
    return str(app.query_one(DataTable).get_cell(source_id, "status"))


def test_stale_source_shows_stale_badge():
    s = FakeSource(id="stale_src", name="Stale Src", update_cadence_days=7)
    app = DataTuiApp(sources=[s], deferred=[], manifest=_manifest({s.id: _past_cadence_entry()}))

    async def scenario():
        async with app.run_test():
            assert "STALE" in _status_cell(app, "stale_src")

    asyncio.run(scenario())


def test_sweep_updates_badge_live():
    """Check-for-updates flips a fresh source to STALE when the publisher moved."""
    s = FakeSource(id="moved", name="Moved", remote="v2")
    app = DataTuiApp(sources=[s], deferred=[], manifest=_manifest({s.id: _fresh_entry("v1")}))

    async def scenario():
        async with app.run_test() as pilot:
            assert "FRESH" in _status_cell(app, "moved")
            await pilot.press("c")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "STALE" in _status_cell(app, "moved")
            assert app.manifest.entry("moved").remote_version == "v2"

    asyncio.run(scenario())


def test_sweep_skips_manual_sources():
    manual = FakeSource(id="ar", name="AR Parcels", legal=_legal(AutomationPolicy.MANUAL_ONLY))
    app = DataTuiApp(sources=[manual], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("c")
            await app.workers.wait_for_complete()
            await pilot.pause()
            # Never probed: no checked_at stamped, badge still MANUAL.
            assert app.manifest.entry("ar").checked_at is None
            assert "MANUAL" in _status_cell(app, "ar")

    asyncio.run(scenario())


def test_attention_panel_populates_and_collapses():
    dead = FakeSource(id="dead", name="Dead Endpoint")
    fresh = FakeSource(id="ok", name="Fine")
    app = DataTuiApp(
        sources=[dead, fresh],
        deferred=[],
        manifest=_manifest(
            {"dead": _entry(status="check_failed", error="503"), "ok": _fresh_entry()}
        ),
    )

    async def scenario():
        async with app.run_test():
            assert any("Dead Endpoint" in line for line in app.attention_lines)
            assert any("endpoint failing" in line for line in app.attention_lines)

    asyncio.run(scenario())

    all_fresh = DataTuiApp(sources=[fresh], deferred=[], manifest=_manifest({"ok": _fresh_entry()}))

    async def collapsed():
        async with all_fresh.run_test():
            assert all_fresh.attention_lines == ["✓ All sources current"]

    asyncio.run(collapsed())


def test_deferred_sources_show_deferred_badge():
    active = FakeSource(id="a", name="Active")
    parked = FakeSource(id="d", name="Parked")
    app = DataTuiApp(sources=[active], deferred=[parked], manifest=_manifest({}))

    async def scenario():
        async with app.run_test():
            assert "DEFERRED" in _status_cell(app, "d")

    asyncio.run(scenario())


def test_real_registry_renders_every_active_source():
    """Every active registry source gets a row — real sources, synthetic manifest."""
    from fetch.registry import all_sources

    sources = all_sources()
    app = DataTuiApp(sources=sources, deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test():
            table = app.query_one(DataTable)
            for s in sources:
                assert str(table.get_cell(s.id, "status")) != ""

    asyncio.run(scenario())
