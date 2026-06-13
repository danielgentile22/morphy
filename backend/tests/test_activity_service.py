"""ActivityService (UI overhaul P3 / #112): the shared activity read model —
event kinds, lead/member/channel/date filters, and the recent-activity digest."""

from __future__ import annotations

from datetime import date

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.activity_service import ActivityService
from backend.app.lead_store import LeadStore

CID = "owner0001"
OTHER = "owner0002"


def _leads(engine: Engine, tenant: int = 1) -> LeadStore:
    return LeadStore(Session(bind=engine, future=True), tenant)


def _svc(engine: Engine, tenant: int = 1) -> ActivityService:
    return ActivityService(
        _leads(engine, tenant),
        owner_name_of=lambda cid: f"Owner {cid}",
        member_name_of=lambda uid: (
            {1: "Daniel", 2: "Michael"}.get(uid, "") if uid is not None else ""
        ),
    )


def _seed(engine: Engine) -> None:
    s = _leads(engine)
    s.append_attempt(
        CID, channel="phone", outcome="left vm", occurred_on=date(2026, 6, 1), logged_by_user_id=1
    )
    s.append_attempt(
        CID,
        channel="email",
        outcome="they replied",
        direction="inbound",
        occurred_on=date(2026, 6, 3),
        logged_by_user_id=2,
    )
    s.upsert(CID, status="researching", logged_by_user_id=1)  # auto-logs a status row
    s.append_attempt(
        OTHER, channel="mail", outcome="sent", occurred_on=date(2026, 5, 20), logged_by_user_id=2
    )


def test_event_kinds_are_derived(engine: Engine) -> None:
    _seed(engine)
    kinds = {(e.cluster_id, e.channel): e.kind for e in _svc(engine).events()}
    assert kinds[(CID, "phone")] == "touch"
    assert kinds[(CID, "email")] == "reply"  # inbound
    assert kinds[(CID, "status")] == "status"


def test_excludes_dismiss_rows(engine: Engine) -> None:
    s = _leads(engine)
    s.append_attempt(CID, channel="dismiss", outcome="dismissed")
    assert all(e.channel != "dismiss" for e in _svc(engine).events())


def test_filter_by_lead_member_channel(engine: Engine) -> None:
    _seed(engine)
    svc = _svc(engine)
    assert all(e.cluster_id == CID for e in svc.events(lead=CID))
    # member 2 logged the inbound reply + the OTHER mail
    by_member = svc.events(member=2)
    assert {e.cluster_id for e in by_member} == {CID, OTHER}
    assert all(e.member_name == "Michael" for e in by_member)
    assert all(e.channel == "phone" for e in svc.events(channel="phone"))


def test_filter_by_date_range(engine: Engine) -> None:
    _seed(engine)
    got = _svc(engine).events(date_from=date(2026, 6, 1), date_to=date(2026, 6, 2))
    assert [e.channel for e in got] == ["phone"]  # only the Jun-1 touch


def test_events_are_newest_first_and_carry_owner_name(engine: Engine) -> None:
    _seed(engine)
    events = _svc(engine).events(lead=CID)
    assert [e.date for e in events] == sorted([e.date for e in events], reverse=True)
    assert all(e.owner_name == f"Owner {CID}" for e in events)


def test_digest_reports_last_contact_and_reply(engine: Engine) -> None:
    _seed(engine)
    d = _svc(engine).digest()
    assert d["last_contact_on"] == "2026-06-01"  # the phone touch (not status/flag)
    assert d["last_reply_on"] == "2026-06-03"


def test_activity_is_tenant_scoped(engine: Engine) -> None:
    _seed(engine)
    assert _svc(engine, 2).events() == []
