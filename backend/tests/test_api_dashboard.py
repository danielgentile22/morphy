"""Dashboard routes + automation wiring over HTTP (UI overhaul P3+P5).

Two gaps the pure-service tests don't cover:

* **#116 auto follow-ups** — the *route* hooks (``POST /attempts`` outbound →
  schedule, inbound → cancel; ``PUT /leads`` status→contacted → schedule;
  ``PUT /settings`` disable → suppress). The rule is unit-tested in isolation
  (``test_auto_followup_rule.py``); here we exercise it end-to-end through the
  API so a wiring regression is caught.
* **#112/#113 read routes** — ``GET /api/stats``, ``/api/activity``,
  ``/api/attention`` assemble the owners-index + LeadStore into the pure
  services (status default, member-name resolution, the ``id`` seam). The
  services are unit-tested over hand-built rows; here we assert the route
  assembly reconciles with seeded data.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import ContactAttempt

from ._helpers import api, auth_header, login

NAT = "nat0000aaaa"
LOC = "loc0000bbbb"

SAMPLE = {
    "schema_version": 1,
    "count": 2,
    "owners": [
        {
            "display_cluster_id": NAT,
            "owner_name": "AMERICAN TOWERS LLC",
            "owner_name_norm": "AMERICAN TOWERS",
            "owner_kind": "llc",
            "states": ["AR", "WV"],
            "n_states": 2,
            "cross_state": True,
            "parcel_count": 12,
            "tower_count": 20,
            "solar_count": 0,
            "total_assessed_value": 1000000.0,
            "max_parcel_score": 0.9,
            "score": 1.15,
            "distress_tier": "distressed",
            "in_oz": True,
            "in_qct": True,
            "persistent_poverty": False,
        },
        {
            "display_cluster_id": LOC,
            "owner_name": "SMITH FAMILY TRUST",
            "owner_name_norm": "SMITH",
            "owner_kind": "trust",
            "states": ["AR"],
            "n_states": 1,
            "cross_state": False,
            "parcel_count": 1,
            "tower_count": 1,
            "solar_count": 0,
            "total_assessed_value": 410000.0,
            "max_parcel_score": 0.8,
            "score": 0.8,
            "distress_tier": "at-risk",
            "in_oz": False,
            "in_qct": False,
            "persistent_poverty": True,
        },
    ],
}


@pytest.fixture
def client() -> TestClient:
    with api(SAMPLE) as (c, _eng, _sender):
        c.headers.update(auth_header(login(c)))
        yield c


def _autos(client: TestClient, cid: str | None = None) -> list[dict]:
    rows = client.get("/api/tasks?source=auto").json()["tasks"]
    return [t for t in rows if cid is None or t["lead_cluster_id"] == cid]


# ── #116: auto follow-up route wiring ─────────────────────────────────────────
def test_outbound_touch_schedules_an_auto_followup(client: TestClient) -> None:
    client.post(
        f"/api/leads/{NAT}/attempts",
        json={"channel": "phone", "outcome": "left vm", "occurred_on": "2026-06-01"},
    )
    autos = _autos(client, NAT)
    assert len(autos) == 1
    t = autos[0]
    assert t["source"] == "auto"
    assert t["lead_cluster_id"] == NAT
    # anchored at the touch date + the default 90-day window
    assert t["due_date"] == (date(2026, 6, 1) + timedelta(days=90)).isoformat()


def test_status_to_contacted_schedules_an_auto_followup(client: TestClient) -> None:
    client.put(f"/api/leads/{LOC}", json={"status": "researching"})
    assert _autos(client, LOC) == []  # researching is not a scheduling trigger
    client.put(f"/api/leads/{LOC}", json={"status": "contacted"})
    assert len(_autos(client, LOC)) == 1


def test_inbound_reply_cancels_the_open_followup(client: TestClient) -> None:
    client.post(
        f"/api/leads/{NAT}/attempts",
        json={"channel": "phone", "occurred_on": "2026-06-01"},
    )
    assert len(_autos(client, NAT)) == 1
    client.post(
        f"/api/leads/{NAT}/attempts",
        json={"channel": "email", "direction": "inbound", "occurred_on": "2026-06-05"},
    )
    assert _autos(client, NAT) == []  # the reply cancelled the chase


def test_disabling_automation_suppresses_scheduling(client: TestClient) -> None:
    r = client.put("/api/settings", json={"auto_followup_enabled": False})
    assert r.json()["auto_followup_enabled"] is False
    client.post(
        f"/api/leads/{LOC}/attempts",
        json={"channel": "phone", "occurred_on": "2026-06-01"},
    )
    assert _autos(client, LOC) == []


def test_window_setting_drives_the_due_date(client: TestClient) -> None:
    client.put("/api/settings", json={"auto_followup_window_days": 30})
    client.post(
        f"/api/leads/{NAT}/attempts",
        json={"channel": "phone", "occurred_on": "2026-06-01"},
    )
    assert _autos(client, NAT)[0]["due_date"] == (date(2026, 6, 1) + timedelta(days=30)).isoformat()


# ── #112/#113: dashboard read-route assembly ──────────────────────────────────
def test_stats_route_reconciles_with_seeded_leads_and_activity(client: TestClient) -> None:
    client.put(f"/api/leads/{NAT}", json={"status": "researching"})
    client.put(f"/api/leads/{NAT}", json={"status": "contacted"})
    client.post(
        f"/api/leads/{NAT}/attempts",
        json={"channel": "phone", "outcome": "vm", "occurred_on": "2026-06-01"},
    )
    client.post(
        f"/api/leads/{NAT}/attempts",
        json={
            "channel": "email",
            "outcome": "called back",
            "direction": "inbound",
            "occurred_on": "2026-06-02",
        },
    )
    s = client.get("/api/stats").json()
    assert s["funnel"]["contacted"] == 1  # NAT advanced; LOC defaults to 'new'
    assert s["volume_by_channel"] == {"phone": 1}  # status rows + inbound excluded
    assert s["reply_rate"] == 1.0  # contacted={NAT}, NAT replied
    assert s["by_state"]["AR"]["contacted"] == 1 and s["by_state"]["WV"]["contacted"] == 1
    assert s["by_member"]  # resolved member name, not empty


def test_activity_route_carries_stable_ids_and_digest(client: TestClient) -> None:
    client.post(
        f"/api/leads/{NAT}/attempts",
        json={"channel": "phone", "outcome": "vm", "occurred_on": "2026-06-01"},
    )
    client.post(
        f"/api/leads/{NAT}/attempts",
        json={
            "channel": "email",
            "outcome": "replied",
            "direction": "inbound",
            "occurred_on": "2026-06-02",
        },
    )
    a = client.get("/api/activity").json()
    assert a["count"] == 2
    assert {e["kind"] for e in a["events"]} == {"touch", "reply"}
    # every event carries a stable PK id (the keyed-render fix) and a resolved
    # owner + member name from the route assembly.
    ids = [e["id"] for e in a["events"]]
    assert all(isinstance(i, int) for i in ids) and len(set(ids)) == 2
    assert all(e["owner_name"] == "AMERICAN TOWERS LLC" for e in a["events"])
    assert all(e["member_name"] for e in a["events"])
    assert a["last_contact_on"] == "2026-06-01"
    assert a["last_reply_on"] == "2026-06-02"


def test_attention_route_surfaces_an_unhandled_reply(client: TestClient) -> None:
    client.post(
        f"/api/leads/{NAT}/attempts",
        json={
            "channel": "email",
            "outcome": "called back",
            "direction": "inbound",
            "occurred_on": "2026-06-02",
        },
    )
    att = client.get("/api/attention").json()
    assert att["count"] >= 1
    assert any(i["cluster_id"] == NAT and i["kind"] == "reply" for i in att["items"])


def test_dashboard_reads_require_auth(client: TestClient) -> None:
    naked = TestClient(client.app)
    assert naked.get("/api/stats").status_code == 401
    assert naked.get("/api/activity").status_code == 401
    assert naked.get("/api/attention").status_code == 401


# ── member-name resolution: null/unknown author → "Unattributed" ──────────────
def test_stats_relabels_null_author_touch_as_unattributed() -> None:
    # A touch with no logged_by_user_id (a legacy row, or a non-attributed
    # system write) must read as "Unattributed" in BY TEAM MEMBER — not the raw
    # "user None" the route used to emit. Inserted directly because the API
    # always stamps the acting principal on touches it creates.
    with api(SAMPLE) as (c, eng, _):
        c.headers.update(auth_header(login(c)))
        with Session(bind=eng, future=True) as s:
            s.add(
                ContactAttempt(
                    tenant_id=1,  # devteam is the first team → tenant 1
                    display_cluster_id=NAT,
                    occurred_on=date(2026, 6, 1),
                    channel="phone",
                    outcome="vm",
                    direction="outbound",
                    logged_by_user_id=None,
                )
            )
            s.commit()
        stats = c.get("/api/stats").json()
        assert stats["by_member"] == {"Unattributed": 1}


def test_dismiss_is_attributed_to_the_acting_user() -> None:
    # The dismiss bookkeeping row now carries the dismissing user (audit trail),
    # rather than a null author.
    with api(SAMPLE) as (c, eng, _):
        c.headers.update(auth_header(login(c)))
        c.post(
            f"/api/leads/{NAT}/attempts",
            json={"channel": "email", "direction": "inbound", "occurred_on": "2026-06-02"},
        )
        c.post("/api/attention/dismiss", json={"cluster_id": NAT})
        with Session(bind=eng, future=True) as s:
            rows = s.scalars(
                select(ContactAttempt).where(ContactAttempt.channel == "dismiss")
            ).all()
        assert len(rows) == 1
        assert rows[0].logged_by_user_id is not None
