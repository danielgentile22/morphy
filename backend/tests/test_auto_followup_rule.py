"""AutoFollowUpRule (UI overhaul P5 / #116, ADR-066/D12): schedule-forward,
cancel-on-reply, eligibility, window + on/off."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.auto_followup_rule import AutoFollowUpRule
from backend.app.lead_store import LeadStore
from backend.app.settings_store import (
    AUTO_FOLLOWUP_ENABLED,
    AUTO_FOLLOWUP_WINDOW_DAYS,
    SettingsStore,
)
from backend.app.task_store import TaskStore

CID = "owner0001"
ANCHOR = date(2026, 6, 1)


def _rule(engine: Engine, tenant: int = 1) -> AutoFollowUpRule:
    s = Session(bind=engine, future=True)
    return AutoFollowUpRule(
        LeadStore(s, tenant),
        TaskStore(s, tenant),
        SettingsStore(s, tenant),
        owner_name_of=lambda cid: f"Owner {cid}",
    )


def _tasks(engine: Engine, tenant: int = 1) -> TaskStore:
    return TaskStore(Session(bind=engine, future=True), tenant)


def test_schedules_a_followup_at_anchor_plus_window(engine: Engine) -> None:
    t = _rule(engine).maybe_schedule(CID, anchor=ANCHOR, status="contacted")
    assert t is not None
    assert t.source == "auto"
    assert t.lead_cluster_id == CID
    assert t.due_date == ANCHOR + timedelta(days=90)  # default window
    assert t.title == "Follow up: Owner owner0001"


def test_idempotent_one_open_followup_per_lead(engine: Engine) -> None:
    _rule(engine).maybe_schedule(CID, anchor=ANCHOR, status="contacted")
    again = _rule(engine).maybe_schedule(CID, anchor=ANCHOR, status="contacted")
    assert again is None  # already one open → no duplicate
    autos = [t for t in _tasks(engine).list() if t.source == "auto"]
    assert len(autos) == 1


def test_not_scheduled_for_resolved_statuses(engine: Engine) -> None:
    for status in ("interested", "in_business", "uninterested"):
        assert _rule(engine).maybe_schedule(CID, anchor=ANCHOR, status=status) is None


def test_not_scheduled_when_reply_already_since_anchor(engine: Engine) -> None:
    LeadStore(Session(bind=engine, future=True), 1).append_attempt(
        CID, channel="email", outcome="hi", direction="inbound", occurred_on=ANCHOR
    )
    assert _rule(engine).maybe_schedule(CID, anchor=ANCHOR, status="contacted") is None


def test_inbound_reply_cancels_the_open_followup(engine: Engine) -> None:
    _rule(engine).maybe_schedule(CID, anchor=ANCHOR, status="contacted")
    assert any(t.source == "auto" for t in _tasks(engine).list())
    cancelled = _rule(engine).cancel_on_reply(CID)
    assert cancelled == 1
    assert not any(t.source == "auto" for t in _tasks(engine).list())


def test_disabled_rule_schedules_nothing(engine: Engine) -> None:
    SettingsStore(Session(bind=engine, future=True), 1).set(AUTO_FOLLOWUP_ENABLED, "0")
    assert _rule(engine).maybe_schedule(CID, anchor=ANCHOR, status="contacted") is None


def test_window_setting_is_honored(engine: Engine) -> None:
    SettingsStore(Session(bind=engine, future=True), 1).set(AUTO_FOLLOWUP_WINDOW_DAYS, "30")
    t = _rule(engine).maybe_schedule(CID, anchor=ANCHOR, status="contacted")
    assert t.due_date == ANCHOR + timedelta(days=30)


def test_followups_are_tenant_scoped(engine: Engine) -> None:
    _rule(engine, 1).maybe_schedule(CID, anchor=ANCHOR, status="contacted")
    # tenant 2 sees no auto task, and its own rule still schedules independently
    assert [t for t in _tasks(engine, 2).list() if t.source == "auto"] == []
    assert _rule(engine, 2).maybe_schedule(CID, anchor=ANCHOR, status="contacted") is not None
