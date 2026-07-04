"""Data TUI slices 1+2+4 (#234/#236/#238): badges, attention, pulls,
failure pane, preprocess stage.

The pure freshness/attention matrix is exercised directly; the app itself
is driven through Textual's pilot (headless) — the repo's first UI tests.
Pilot tests wrap their async body in ``asyncio.run`` so no async test
plugin is needed (PRD #233: Textual is the one new dependency). The
refresh planner behind the preprocess preselection has its own unit
suite in ``test_refresh_planner.py``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from data_tui import manual as manual_mod
from data_tui.app import ActivityEvent, DataTuiApp, filter_activity
from data_tui.freshness import (
    SEV_DEAD,
    SEV_MISSING,
    SEV_STALE,
    attention_items,
    badge_for,
)
from data_tui.manual import InstallScreen, WalkthroughScreen
from fetch import storage as storage_mod
from fetch.base import FetchResult
from fetch.legal import AutomationPolicy, CommercialUse, LegalInfo
from fetch.manifest import Manifest, SourceEntry
from fetch.walkthroughs import ManualStep, ManualWalkthrough
from textual.widgets import DataTable, Input

FAIL_URL = "https://example.com/data.zip"


@pytest.fixture(autouse=True)
def _no_fetch_log(monkeypatch):
    """Keep test sweeps out of the real data/fetch.log."""
    monkeypatch.setattr("fetch.puller.log_event", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _notifications(monkeypatch):
    """Capture desktop notifications instead of running osascript."""
    sent: list[tuple] = []
    monkeypatch.setattr("data_tui.app.notify_send", lambda *a: sent.append(a))
    monkeypatch.setattr("data_tui.deploy_ui.notify_send", lambda *a: sent.append(a))
    return sent


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
    """Duck-typed DataSource — what badges, attention, check_one, fetch_one read."""

    id: str = "fake"
    name: str = "Fake"
    category: str = "Towers"
    coverage: str = "National"
    update_cadence_days: int | None = 30
    legal: LegalInfo = field(default_factory=lambda: _legal(AutomationPolicy.ALLOWED))
    remote: str = "v1"
    fail_check: bool = False
    fail_fetch: bool = False
    fetch_calls: int = 0
    walkthrough: ManualWalkthrough | None = None

    @property
    def is_manual_only(self) -> bool:
        return self.legal.automation == AutomationPolicy.MANUAL_ONLY

    @property
    def needs_credentials(self) -> bool:
        return self.legal.automation == AutomationPolicy.CREDENTIALED

    def credentials_available(self) -> bool:
        return True

    def remote_version(self) -> str:
        if self.fail_check:
            raise RuntimeError(f"HEAD {FAIL_URL} → HTTP 500")
        return self.remote

    def fetch(self, dest_dir: Path, progress) -> FetchResult:
        self.fetch_calls += 1
        if self.fail_fetch:
            raise RuntimeError(f"download {FAIL_URL} failed after retries: HTTP 500")
        p = dest_dir / "data.bin"
        p.write_bytes(b"x" * 100)
        progress(10, 100, "data.bin")
        progress(100, 100, "data.bin")
        return FetchResult(files=[p], remote_version=self.remote, total_bytes=100)

    def validate(self, files: list[Path]) -> None:
        pass

    def manual_walkthrough(self):
        return self.walkthrough


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


# ── slice 2 (#236): pull flow, failure pane, activity log ────────────────


def test_filter_activity_modes():
    events = [
        ActivityEvent("10:00:00", "a", "check ok", False),
        ActivityEvent("10:00:01", "b", "fetch failed — boom", True),
        ActivityEvent("10:00:02", "a", "fetch ok", False),
    ]
    assert filter_activity(events, "all") == events
    assert [e.source_id for e in filter_activity(events, "errors")] == ["b"]
    assert [e.message for e in filter_activity(events, "source", "a")] == ["check ok", "fetch ok"]


def test_pull_now_advances_progress_and_flips_fresh(monkeypatch, tmp_path, _notifications):
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    s = FakeSource(id="pullme", name="Pull Me")
    app = DataTuiApp(sources=[s], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            app.query_one(DataTable).move_cursor(row=1)  # row 0 is the category header
            await pilot.pause()
            await pilot.press("p")
            await app.workers.wait_for_complete()
            await pilot.pause()
            # The progress line advanced through byte counts to completion.
            assert any("10 B / 100 B" in line for line in app.job_lines), app.job_lines
            assert any("100 B / 100 B" in line for line in app.job_lines), app.job_lines
            assert any("pull finished" in line for line in app.job_lines)
            assert "FRESH" in _status_cell(app, "pullme")
            assert app.manifest.entry("pullme").status == "ok"
            assert (tmp_path / "pullme" / "current" / "data.bin").exists()

    asyncio.run(scenario())
    assert _notifications and "complete" in _notifications[-1][0]


def test_failed_pull_populates_failure_pane(monkeypatch, tmp_path, _notifications):
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    s = FakeSource(id="failing", name="Failing Src", fail_fetch=True)
    app = DataTuiApp(sources=[s], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            app.query_one(DataTable).move_cursor(row=1)
            await pilot.pause()
            await pilot.press("p")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "DEAD" in _status_cell(app, "failing")
            # Pane shows the exact URL, error, and last-worked date.
            assert any(FAIL_URL in line for line in app.detail_lines), app.detail_lines
            assert any("HTTP 500" in line for line in app.detail_lines)
            assert any("Last successful fetch: never" in line for line in app.detail_lines)
            le = app.manifest.entry("failing").last_error
            assert le["url"] == FAIL_URL

    asyncio.run(scenario())
    assert _notifications and "failed" in _notifications[-1][0]


def test_pull_stale_targets_only_stale_and_missing_auto_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    stale = FakeSource(id="stale1", name="Stale One", update_cadence_days=7)
    fresh = FakeSource(id="fresh1", name="Fresh One")
    missing = FakeSource(id="miss1", name="Missing One")
    manual = FakeSource(id="man1", name="Manual One", legal=_legal(AutomationPolicy.MANUAL_ONLY))
    app = DataTuiApp(
        sources=[stale, fresh, missing, manual],
        deferred=[],
        manifest=_manifest({"stale1": _past_cadence_entry(), "fresh1": _fresh_entry()}),
    )

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("P")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert stale.fetch_calls == 1
            assert missing.fetch_calls == 1
            assert fresh.fetch_calls == 0
            assert manual.fetch_calls == 0

    asyncio.run(scenario())


def test_activity_log_toggles_and_filters_errors():
    ok = FakeSource(id="ok_src", name="OK Src")
    bad = FakeSource(id="bad_src", name="Bad Src", fail_check=True)
    app = DataTuiApp(sources=[ok, bad], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("c")
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("l")
            await pilot.pause()
            assert app.log_lines[0].startswith("Activity (all) — 2 events")
            await pilot.press("f")
            await pilot.pause()
            assert app.log_lines[0].startswith("Activity (errors) — 1 events")
            assert any("bad_src" in line and "check failed" in line for line in app.log_lines)

    asyncio.run(scenario())


# ── slice 3 (#237): walkthrough screen + install-from-file ───────────────


def _walkthrough() -> ManualWalkthrough:
    return ManualWalkthrough(
        landing_page_url="https://example.com/landing",
        steps=[
            ManualStep(
                title="Open portal",
                body="Go to the parcel portal",
                deep_link="https://example.com/step1",
            ),
            ManualStep(title="Request export", body="Click 'Export statewide'"),
            ManualStep(title="Install", body="Install the downloaded files"),
        ],
        expected_files=["data.bin"],
    )


def _manual_source(**kw) -> FakeSource:
    kw.setdefault("id", "ar")
    kw.setdefault("name", "AR Parcels")
    kw.setdefault("legal", _legal(AutomationPolicy.MANUAL_ONLY))
    kw.setdefault("walkthrough", _walkthrough())
    return FakeSource(**kw)


def test_walkthrough_advances_steps_and_opens_deep_link(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(manual_mod.webbrowser, "open", opened.append)
    s = _manual_source()
    app = DataTuiApp(sources=[s], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            app.query_one(DataTable).move_cursor(row=1)
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            scr = app.screen
            assert isinstance(scr, WalkthroughScreen)
            assert any("Step 1 of 3: Open portal" in line for line in scr.lines)
            await pilot.press("o")
            assert opened == ["https://example.com/step1"]
            await pilot.press("n")
            assert any("Step 2 of 3: Request export" in line for line in scr.lines)
            await pilot.press("b")
            assert any("Step 1 of 3" in line for line in scr.lines)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, WalkthroughScreen)

    asyncio.run(scenario())


def test_walkthrough_finish_verifies_and_flips_table(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    s = _manual_source()
    app = DataTuiApp(sources=[s], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            app.query_one(DataTable).move_cursor(row=1)
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            await pilot.press("n")
            await pilot.press("n")
            # Finishing with an empty current/ stays in-screen with an error.
            await pilot.press("n")
            await pilot.pause()
            assert isinstance(app.screen, WalkthroughScreen)
            assert any("No files found" in line for line in app.screen.lines)
            cur = tmp_path / "ar" / "current"
            cur.mkdir(parents=True, exist_ok=True)
            (cur / "data.bin").write_bytes(b"x")
            await pilot.press("n")
            await pilot.pause()
            assert not isinstance(app.screen, WalkthroughScreen)
            assert app.manifest.entry("ar").local_version == "manual"
            assert "FRESH" in _status_cell(app, "ar")

    asyncio.run(scenario())


def test_walkthrough_reachable_after_failed_auto_fetch(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    s = FakeSource(id="rotted", name="Rotted Src", fail_fetch=True, walkthrough=_walkthrough())
    app = DataTuiApp(sources=[s], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            app.query_one(DataTable).move_cursor(row=1)
            await pilot.pause()
            await pilot.press("p")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "DEAD" in _status_cell(app, "rotted")
            await pilot.press("w")
            await pilot.pause()
            assert isinstance(app.screen, WalkthroughScreen)

    asyncio.run(scenario())


def test_walkthrough_unavailable_without_steps():
    s = FakeSource(id="auto", name="Auto Src")  # no walkthrough
    app = DataTuiApp(sources=[s], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            app.query_one(DataTable).move_cursor(row=1)
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            assert not isinstance(app.screen, WalkthroughScreen)
            assert any("no manual walkthrough" in line for line in app.job_lines)

    asyncio.run(scenario())


def test_install_from_file_updates_table(monkeypatch, tmp_path):
    import zipfile

    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path / "raw")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    csv = downloads / "My data.csv"  # space exercises dragged-path quoting
    csv.write_text("a,b")
    zp = downloads / "bundle.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("inner/one.txt", b"1")

    s = _manual_source(id="man1", name="Manual One")
    app = DataTuiApp(sources=[s], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            app.query_one(DataTable).move_cursor(row=1)
            await pilot.pause()
            await pilot.press("i")
            await pilot.pause()
            assert isinstance(app.screen, InstallScreen)
            app.screen.query_one(Input).value = f'"{csv}" {zp}'
            await pilot.press("enter")
            await pilot.pause()
            cur = tmp_path / "raw" / "man1" / "current"
            assert (cur / "My data.csv").read_text() == "a,b"
            assert (cur / "bundle" / "inner" / "one.txt").exists()
            assert app.manifest.entry("man1").local_version == "manual"
            assert "FRESH" in _status_cell(app, "man1")
            assert any("manual install ok" in e.message for e in app.activity)

    asyncio.run(scenario())


# ── slice 4 (#238): preprocess stage ─────────────────────────────────────


def _wv_source(**kw) -> FakeSource:
    kw.setdefault("id", "wv_parcels")
    kw.setdefault("name", "WV Parcels")
    kw.setdefault("coverage", "State: West Virginia")
    return FakeSource(**kw)


def _outcome(**kw):
    from types import SimpleNamespace

    base = dict(
        normalized_ok=["wv_parcels"],
        normalized_failed=[],
        normalized_skipped=[],
        normalized_unavailable=[],
        composed_ok=["54"],
        composed_failed=[],
        failed_steps=[],
        duration_seconds=1.0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_completed_pull_preselects_state_in_preprocess_screen(monkeypatch, tmp_path):
    """Acceptance pilot: pull WV parcels → open preprocess → WV preselected."""
    from data_tui.preprocess_ui import PreprocessScreen
    from preprocess.manifest import PreprocessManifest
    from textual.widgets import SelectionList

    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    s = _wv_source()
    app = DataTuiApp(
        sources=[s], deferred=[], manifest=_manifest({}), pre_manifest=PreprocessManifest()
    )

    async def scenario():
        async with app.run_test() as pilot:
            app.query_one(DataTable).move_cursor(row=1)
            await pilot.pause()
            await pilot.press("p")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "FRESH" in _status_cell(app, "wv_parcels")
            await pilot.press("r")
            await pilot.pause()
            scr = app.screen
            assert isinstance(scr, PreprocessScreen)
            assert list(scr.query_one(SelectionList).selected) == ["54"]
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, PreprocessScreen)
            assert not app._preprocess_running

    asyncio.run(scenario())


def test_preprocess_runs_in_background_with_progress_and_notifies(monkeypatch, _notifications):
    from preprocess.manifest import PreprocessManifest

    ran_states: list[list[str]] = []

    def fake_pipeline(states, progress_callback):
        ran_states.append(states)
        progress_callback("normalize_start", "wv_parcels", {})
        progress_callback("normalize_ok", "wv_parcels", {"rows": 12345, "bytes": 1})
        progress_callback("compose_start", "54", {"name": "West Virginia"})
        progress_callback("compose_ok", "54", {"counts": {"parcels": 10}})
        progress_callback("step_ok", "app_assets", {})
        return _outcome()

    monkeypatch.setattr("data_tui.app.run_preprocess_pipeline", fake_pipeline)
    s = _wv_source()
    app = DataTuiApp(
        sources=[s],
        deferred=[],
        manifest=_manifest({"wv_parcels": _fresh_entry()}),
        pre_manifest=PreprocessManifest(),
    )

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("r")
            await pilot.pause()
            await pilot.press("s")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert ran_states == [["54"]]
            # Per-source and per-state progress lines advanced the job pane.
            assert any("normalize wv_parcels" in line for line in app.job_lines)
            assert any("12,345 rows" in line for line in app.job_lines)
            assert any("compose state 54" in line for line in app.job_lines)
            assert any(
                "✓ preprocess finished — 1 normalized, 1 composed" in line for line in app.job_lines
            )

    asyncio.run(scenario())
    assert _notifications and "complete" in _notifications[-1][0]


def test_preprocess_failure_notifies_and_logs_error(monkeypatch, _notifications):
    from preprocess.manifest import PreprocessManifest

    def fake_pipeline(states, progress_callback):
        progress_callback("compose_fail", "54", {"error": "boom"})
        return _outcome(composed_ok=[], composed_failed=["54"])

    monkeypatch.setattr("data_tui.app.run_preprocess_pipeline", fake_pipeline)
    app = DataTuiApp(
        sources=[_wv_source()],
        deferred=[],
        manifest=_manifest({"wv_parcels": _fresh_entry()}),
        pre_manifest=PreprocessManifest(),
    )

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("r")
            await pilot.pause()
            await pilot.press("s")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert any("✗ compose state 54: boom" in line for line in app.job_lines)
            assert any("preprocess finished" in line and "failed" in line for line in app.job_lines)
            assert any(e.error and "compose state 54" in e.message for e in app.activity)
            assert not app._preprocess_running

    asyncio.run(scenario())
    assert _notifications and "failed" in _notifications[-1][0]


def test_preprocess_with_no_data_shows_hint():
    from data_tui.preprocess_ui import PreprocessScreen
    from preprocess.manifest import PreprocessManifest

    app = DataTuiApp(
        sources=[_wv_source()],
        deferred=[],
        manifest=_manifest({}),
        pre_manifest=PreprocessManifest(),
    )

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("r")
            await pilot.pause()
            assert not isinstance(app.screen, PreprocessScreen)
            assert any("No states with data to preprocess" in line for line in app.job_lines)

    asyncio.run(scenario())


# ── slice 5 (#239): verify + confirm-gated deploy ────────────────────────


def _mk_composite(root: Path, parcel: int = 1000) -> Path:
    import json

    state = root / "54"
    state.mkdir(parents=True, exist_ok=True)
    (root / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "states": [
                    {
                        "fips": "54",
                        "abbr": "WV",
                        "name": "West Virginia",
                        "counts": {"parcel": parcel, "tower": 100},
                    }
                ],
            }
        )
    )
    (root / "owners_index.json").write_text(
        json.dumps({"schema_version": 5, "count": 500, "generated_at": "2026-07-01T00:00:00+00:00"})
    )
    (state / "towers.parquet").write_bytes(b"t")
    return root


def _stub_script(tmp_path: Path, name: str, fail_on: str = "") -> tuple[Path, Path]:
    import stat

    log = tmp_path / f"{name}.log"
    script = tmp_path / name
    script.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'echo "out: $@"\n'
        f'[ -n "{fail_on}" ] && [ "$1" = "{fail_on}" ] && exit 1\n'
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script, log


def _deploy_env(tmp_path, monkeypatch, *, receipt: bool = True, fail_on: str = ""):
    """Fixture composite + stub deploy/restart scripts wired into the module
    constants DeployScreen resolves at mount (RAW_ROOT monkeypatch pattern)."""
    from data_tui import deploy as deploy_mod
    from data_tui import verify as verify_mod
    from data_tui.verify import snapshot, write_receipt

    comp = _mk_composite(tmp_path / "composite")
    receipt_path = tmp_path / "deploy_receipt.json"
    script, deploy_log = _stub_script(tmp_path, "deploy.sh", fail_on)
    restart, restart_log = _stub_script(tmp_path, "fly")
    monkeypatch.setattr(verify_mod, "COMPOSITE_ROOT", comp)
    monkeypatch.setattr(verify_mod, "RECEIPT_PATH", receipt_path)
    monkeypatch.setattr(deploy_mod, "DEPLOY_SCRIPT", script)
    monkeypatch.setattr(deploy_mod, "RESTART_ARGV", (str(restart), "restart"))
    if receipt:
        write_receipt(snapshot(comp), receipt_path)
    return comp, receipt_path, deploy_log, restart_log


def _log_calls(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def test_deploy_happy_path_dry_run_confirm_apply_receipt(tmp_path, monkeypatch, _notifications):
    from data_tui.deploy_ui import DeployScreen

    _, receipt_path, deploy_log, restart_log = _deploy_env(tmp_path, monkeypatch)
    app = DataTuiApp(sources=[FakeSource()], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("v")
            await pilot.pause()
            scr = app.screen
            assert isinstance(scr, DeployScreen)
            assert all("✗" not in line for line in scr.lines), scr.lines
            assert "[d] dry-run" in scr.status_line
            await pilot.press("d")
            await app.workers.wait_for_complete()
            await pilot.pause()
            # Dry-run output shown first; apply waits for confirmation.
            assert "[dry-run] out: data" in scr.output_lines
            assert "APPLY TO PROD" in scr.status_line
            assert _log_calls(deploy_log) == ["data"]
            await pilot.press("a")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "[sync] out: data --apply" in scr.output_lines
            assert "[smoke] out: smoke" in scr.output_lines
            assert "✓ SMOKE PASSED" in scr.output_lines
            # Sync strictly before smoke; owners unchanged → no restart.
            assert _log_calls(deploy_log) == ["data", "data --apply", "smoke"]
            assert _log_calls(restart_log) == []
            assert receipt_path.exists()
            assert any("deploy complete" in e.message for e in app.activity)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, DeployScreen)
            assert any("deploy complete" in line for line in app.job_lines)

    asyncio.run(scenario())
    assert _notifications and "deploy complete" in _notifications[-1][0]


def test_failed_verify_blocks_deploy_until_logged_override(tmp_path, monkeypatch):
    from data_tui.deploy_ui import DeployScreen
    from data_tui.verify import snapshot, write_receipt

    comp, receipt_path, deploy_log, _ = _deploy_env(tmp_path, monkeypatch, receipt=False)
    # Receipt claims twice the parcels — the fresh composite reads as a 50% drop.
    inflated = snapshot(comp)
    inflated["state_counts"]["54"]["parcel"] = 2000
    write_receipt(inflated, receipt_path)
    app = DataTuiApp(sources=[FakeSource()], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("v")
            await pilot.pause()
            scr = app.screen
            assert isinstance(scr, DeployScreen)
            assert any("✗ counts:54:parcel" in line for line in scr.lines)
            assert "VERIFY FAILED" in scr.status_line
            # Blocked: [d] does nothing until the override is logged.
            await pilot.press("d")
            await pilot.pause()
            assert scr.output_lines == []
            assert _log_calls(deploy_log) == []
            await pilot.press("o")
            await pilot.pause()
            assert any(
                e.error and "verify override" in e.message and "counts:54:parcel" in e.message
                for e in app.activity
            )
            await pilot.press("d")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert _log_calls(deploy_log) == ["data"]
            assert "APPLY TO PROD" in scr.status_line

    asyncio.run(scenario())


def test_smoke_failure_is_unmissable_and_receipt_not_written(tmp_path, monkeypatch, _notifications):
    from data_tui.verify import load_receipt

    _, receipt_path, _, _ = _deploy_env(tmp_path, monkeypatch, fail_on="smoke")
    before = load_receipt(receipt_path)
    app = DataTuiApp(sources=[FakeSource()], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("v")
            await pilot.pause()
            await pilot.press("d")
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("a")
            await app.workers.wait_for_complete()
            await pilot.pause()
            scr = app.screen
            assert any("SMOKE FAILED" in line for line in scr.output_lines)
            assert "SMOKE FAILED" in scr.status_line
            assert any(e.error and "SMOKE FAILED" in e.message for e in app.activity)

    asyncio.run(scenario())
    assert load_receipt(receipt_path) == before  # failed deploy leaves the baseline alone
    assert _notifications and "FAILED" in _notifications[-1][0]


def test_first_deploy_reports_without_blocking_and_restarts(tmp_path, monkeypatch):
    from data_tui.deploy_ui import DeployScreen
    from data_tui.verify import load_receipt

    _, receipt_path, deploy_log, restart_log = _deploy_env(tmp_path, monkeypatch, receipt=False)
    app = DataTuiApp(sources=[FakeSource()], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("v")
            await pilot.pause()
            scr = app.screen
            assert isinstance(scr, DeployScreen)
            assert any("no deploy receipt yet" in line for line in scr.lines)
            assert "[d] dry-run" in scr.status_line  # first run never blocks
            await pilot.press("d")
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("a")
            await app.workers.wait_for_complete()
            await pilot.pause()
            # No receipt → owners considered changed → restart between sync and smoke.
            assert _log_calls(deploy_log) == ["data", "data --apply", "smoke"]
            assert _log_calls(restart_log) == ["restart"]
            receipt = load_receipt(receipt_path)
            assert receipt and receipt["state_counts"]["54"]["parcel"] == 1000

    asyncio.run(scenario())


def test_install_from_file_rejects_missing_path(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_mod, "RAW_ROOT", tmp_path)
    s = _manual_source()
    app = DataTuiApp(sources=[s], deferred=[], manifest=_manifest({}))

    async def scenario():
        async with app.run_test() as pilot:
            app.query_one(DataTable).move_cursor(row=1)
            await pilot.pause()
            await pilot.press("i")
            await pilot.pause()
            app.screen.query_one(Input).value = "/nope/missing.zip"
            await pilot.press("enter")
            await pilot.pause()
            # Stays open with the error shown; manifest untouched.
            assert isinstance(app.screen, InstallScreen)
            assert app.manifest.entry("ar").local_version is None
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, InstallScreen)

    asyncio.run(scenario())


def test_run_preprocess_pipeline_forwards_to_run_all(monkeypatch):
    """The TUI worker is a thin shell (#259/PRD #233): it just forwards the
    multi-state selection to preprocess.runner.run_all, which owns the
    canonical step order."""
    from data_tui.app import run_preprocess_pipeline

    calls: dict = {}

    def fake_run_all(*, states, progress_callback):
        calls["states"] = states
        calls["cb"] = progress_callback
        return "outcome-sentinel"

    monkeypatch.setattr("preprocess.runner.run_all", fake_run_all)

    def cb(*_a):
        pass

    out = run_preprocess_pipeline(["05", "54"], cb)
    assert out == "outcome-sentinel"
    assert calls["states"] == ["05", "54"]
    assert calls["cb"] is cb
