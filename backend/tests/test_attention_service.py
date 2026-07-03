"""AttentionService (UI overhaul P2 / #111, ADR-065/D10): unhandled inbound
replies + overdue tasks; clearing on newer activity / dismiss; tenant scope."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.attention_service import DISMISS_CHANNEL, AttentionService
from backend.app.lead_store import LeadStore
from backend.app.task_store import TaskStore

CID = "owner0001"
TODAY = date(2026, 6, 6)


def _svc(engine: Engine, tenant: int, user_id: int = 1) -> AttentionService:
    sess = Session(bind=engine, future=True)
    return AttentionService(
        LeadStore(sess, tenant),
        TaskStore(sess, tenant),
        user_id=user_id,
        today=TODAY,
        owner_name_of=lambda cid: f"Owner {cid}",
    )


def _leads(engine: Engine, tenant: int) -> LeadStore:
    return LeadStore(Session(bind=engine, future=True), tenant)


def _tasks(engine: Engine, tenant: int) -> TaskStore:
    return TaskStore(Session(bind=engine, future=True), tenant)


# ── unhandled replies ─────────────────────────────────────────────────────────
def test_inbound_reply_with_no_newer_activity_is_unhandled(engine: Engine) -> None:
    _leads(engine, 1).append_attempt(CID, channel="email", outcome="hi", direction="inbound")
    items = _svc(engine, 1).items()
    assert [i.kind for i in items] == ["reply"]
    assert items[0].cluster_id == CID
    assert items[0].owner_name == f"Owner {CID}"


def test_reply_clears_when_a_newer_touch_is_logged(engine: Engine) -> None:
    store = _leads(engine, 1)
    store.append_attempt(
        CID, channel="email", outcome="hi", direction="inbound", occurred_on=date(2026, 6, 1)
    )
    # a later outbound touch = "acted on it" → clears
    store.append_attempt(CID, channel="phone", outcome="called back", occurred_on=date(2026, 6, 2))
    assert _svc(engine, 1).unhandled_replies() == []


def test_outbound_only_is_not_attention(engine: Engine) -> None:
    _leads(engine, 1).append_attempt(CID, channel="phone", outcome="left vm")
    assert _svc(engine, 1).unhandled_replies() == []


def test_dismiss_clears_the_reply(engine: Engine) -> None:
    # Dismissal is just a newer activity row (channel='dismiss') — the rule the
    # /api/attention/dismiss route applies via the lead store.
    _leads(engine, 1).append_attempt(CID, channel="email", outcome="hi", direction="inbound")
    assert len(_svc(engine, 1).items()) == 1
    _leads(engine, 1).append_attempt(CID, channel=DISMISS_CHANNEL, outcome="dismissed")
    assert _svc(engine, 1).unhandled_replies() == []


# ── overdue tasks ─────────────────────────────────────────────────────────────
def test_overdue_unassigned_task_is_attention(engine: Engine) -> None:
    _tasks(engine, 1).create(title="follow up", due_date=TODAY - timedelta(days=1))
    items = _svc(engine, 1).overdue_tasks()
    assert len(items) == 1 and items[0].kind == "overdue_task"


def test_task_due_today_or_done_is_not_overdue(engine: Engine) -> None:
    s = _tasks(engine, 1)
    s.create(title="due today", due_date=TODAY)
    s.create(title="done late", due_date=TODAY - timedelta(days=2), status="done")
    assert _svc(engine, 1).overdue_tasks() == []


def test_overdue_task_assigned_to_someone_else_is_not_mine(engine: Engine) -> None:
    _tasks(engine, 1).create(
        title="theirs", due_date=TODAY - timedelta(days=1), assignee_user_id=99
    )
    # user 1 doesn't see user 99's overdue task…
    assert _svc(engine, 1, user_id=1).overdue_tasks() == []
    # …but user 99 does.
    assert len(_svc(engine, 1, user_id=99).overdue_tasks()) == 1


def test_my_overdue_task_is_attention(engine: Engine) -> None:
    _tasks(engine, 1).create(title="mine", due_date=TODAY - timedelta(days=3), assignee_user_id=1)
    assert len(_svc(engine, 1, user_id=1).overdue_tasks()) == 1


# ── composition + tenant scope ────────────────────────────────────────────────
def test_feed_combines_replies_and_overdue_tasks(engine: Engine) -> None:
    _leads(engine, 1).append_attempt(CID, channel="email", outcome="hi", direction="inbound")
    _tasks(engine, 1).create(title="overdue", due_date=TODAY - timedelta(days=1))
    assert len(_svc(engine, 1).items()) == 2


def test_attention_is_tenant_scoped(engine: Engine) -> None:
    _leads(engine, 1).append_attempt(CID, channel="email", outcome="hi", direction="inbound")
    _tasks(engine, 1).create(title="overdue", due_date=TODAY - timedelta(days=1))
    assert _svc(engine, 2).items() == []
