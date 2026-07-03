"""Route-level two-tenant isolation for the surfaces that had none (#261).

Extends ``test_tenant_isolation_api.py`` (leads/candidates/counts) to every
remaining tenant-scoped surface: tasks, antennas, scoring presets, tenant
settings, activity, stats, attention, and users. Same posture: two users on
two teams, authenticated through the real login route, asserting "team A
cannot read / write / list team B's data".

Run with ``pytest -k tenant_isolation``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from .._helpers import api, auth_header, seed_credential

CID = "nat0000aaaa"

SAMPLE = {
    "schema_version": 1,
    "count": 1,
    "owners": [
        {
            "display_cluster_id": CID,
            "owner_name": "AMERICAN TOWERS LLC",
            "owner_name_norm": "AMERICAN TOWERS",
            "owner_kind": "llc",
            "states": ["AR"],
            "n_states": 1,
            "cross_state": False,
            "parcel_count": 1,
            "tower_count": 3,
            "solar_count": 0,
            "total_assessed_value": 1.0,
            "max_parcel_score": 0.5,
            "score": 0.5,
            "distress_tier": "at-risk",
            "in_oz": False,
            "in_qct": False,
            "persistent_poverty": False,
        }
    ],
}


@pytest.fixture
def two_tenants() -> Iterator[tuple[TestClient, dict, dict]]:
    """A client plus per-tenant auth headers for two users on two teams
    (same fixture shape as ``test_tenant_isolation_api.py``)."""
    with api(SAMPLE) as (client, eng, _sender):
        seed_credential(eng, "user-a", "pw-a", "team-a")
        seed_credential(eng, "user-b", "pw-b", "team-b")

        def login(username: str, password: str) -> dict:
            r = client.post("/api/auth/login", json={"username": username, "password": password})
            assert r.status_code == 200, r.text
            client.cookies.clear()  # header-driven identities — the cookie would outrank them
            return auth_header(r.json()["access_token"])

        yield client, login("user-a", "pw-a"), login("user-b", "pw-b")


# ── tasks ─────────────────────────────────────────────────────────────────────
@pytest.mark.tenant_isolation
def test_tasks_are_invisible_across_tenants(two_tenants) -> None:
    client, a, b = two_tenants
    task_id = client.post("/api/tasks", headers=a, json={"title": "call A's owner"}).json()["id"]

    assert client.get("/api/tasks", headers=b).json()["tasks"] == []
    assert client.get(f"/api/tasks/{task_id}", headers=b).status_code == 404
    assert (
        client.put(f"/api/tasks/{task_id}", headers=b, json={"title": "hijack"}).status_code == 404
    )
    assert client.delete(f"/api/tasks/{task_id}", headers=b).status_code == 404
    # A's task survives B's attempts untouched.
    a_task = client.get(f"/api/tasks/{task_id}", headers=a).json()
    assert a_task["title"] == "call A's owner"


# ── antennas ──────────────────────────────────────────────────────────────────
@pytest.mark.tenant_isolation
def test_antenna_state_is_per_tenant(two_tenants) -> None:
    client, a, b = two_tenants
    client.put(
        "/api/antennas/1234567",
        headers=a,
        json={"archived": True, "notes": "A's private note"},
    )

    b_view = client.get("/api/antennas/1234567", headers=b).json()
    assert b_view["archived"] is False  # B sees the unedited default
    assert b_view["notes"] == ""
    assert client.get("/api/antennas/archived", headers=b).json()["asrs"] == []
    a_archived = client.get("/api/antennas/archived", headers=a).json()["asrs"]
    assert a_archived == ["1234567"]


# ── scoring presets ───────────────────────────────────────────────────────────
@pytest.mark.tenant_isolation
def test_scoring_presets_are_per_tenant(two_tenants) -> None:
    client, a, b = two_tenants
    preset_id = client.post(
        "/api/scoring-presets",
        headers=a,
        json={"name": "A's weights", "config": {"useDefault": False}, "is_default": True},
    ).json()["id"]

    assert client.get("/api/scoring-presets", headers=b).json()["presets"] == []
    assert client.post(f"/api/scoring-presets/{preset_id}/default", headers=b).status_code == 404
    assert client.delete(f"/api/scoring-presets/{preset_id}", headers=b).status_code == 404
    a_presets = client.get("/api/scoring-presets", headers=a).json()["presets"]
    assert [p["name"] for p in a_presets] == ["A's weights"]


# ── tenant settings ───────────────────────────────────────────────────────────
@pytest.mark.tenant_isolation
def test_tenant_settings_are_per_tenant(two_tenants) -> None:
    client, a, b = two_tenants
    client.put(
        "/api/settings",
        headers=a,
        json={"auto_followup_enabled": False, "auto_followup_window_days": 7},
    )

    b_settings = client.get("/api/settings", headers=b).json()
    assert b_settings["auto_followup_enabled"] is True  # B still reads defaults
    assert b_settings["auto_followup_window_days"] == 90
    a_settings = client.get("/api/settings", headers=a).json()
    assert (a_settings["auto_followup_enabled"], a_settings["auto_followup_window_days"]) == (
        False,
        7,
    )


# ── activity + stats ──────────────────────────────────────────────────────────
@pytest.mark.tenant_isolation
def test_activity_stream_is_per_tenant(two_tenants) -> None:
    client, a, b = two_tenants
    client.post(
        f"/api/leads/{CID}/attempts",
        headers=a,
        json={"channel": "call", "outcome": "no answer"},
    )

    assert client.get("/api/activity", headers=b).json()["events"] == []
    a_events = client.get("/api/activity", headers=a).json()["events"]
    assert [e["channel"] for e in a_events] == ["call"]


@pytest.mark.tenant_isolation
def test_stats_count_only_own_tenant_activity(two_tenants) -> None:
    client, a, b = two_tenants
    client.post(f"/api/leads/{CID}/attempts", headers=a, json={"channel": "call"})

    assert client.get("/api/stats", headers=b).json()["activity_total"] == 0
    assert client.get("/api/stats", headers=a).json()["activity_total"] == 1


# ── attention ─────────────────────────────────────────────────────────────────
@pytest.mark.tenant_isolation
def test_attention_feed_is_per_tenant(two_tenants) -> None:
    client, a, b = two_tenants
    # A receives a reply → an unhandled-reply attention item for A only.
    client.post(
        f"/api/leads/{CID}/attempts",
        headers=a,
        json={"channel": "email", "direction": "inbound"},
    )

    assert client.get("/api/attention", headers=b).json()["items"] == []
    assert client.get("/api/attention", headers=a).json()["count"] == 1

    # B "dismissing" the same cluster id writes into B's board only —
    # A's attention item must survive.
    r = client.post("/api/attention/dismiss", headers=b, json={"cluster_id": CID})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert client.get("/api/attention", headers=a).json()["count"] == 1


# ── users ─────────────────────────────────────────────────────────────────────
@pytest.mark.tenant_isolation
def test_user_roster_is_per_tenant(two_tenants) -> None:
    client, a, b = two_tenants
    a_users = client.get("/api/users", headers=a).json()["users"]
    b_users = client.get("/api/users", headers=b).json()["users"]
    assert [u["email"] for u in a_users] == ["user-a"]
    assert [u["email"] for u in b_users] == ["user-b"]


@pytest.mark.tenant_isolation
def test_display_name_edit_stays_in_own_tenant(two_tenants) -> None:
    client, a, b = two_tenants
    client.put("/api/me", headers=a, json={"display_name": "Alice"})

    assert client.get("/api/auth/me", headers=a).json()["display_name"] == "Alice"
    assert client.get("/api/auth/me", headers=b).json()["display_name"] == ""
    assert [u["name"] for u in client.get("/api/users", headers=b).json()["users"]] == ["user-b"]


@pytest.mark.tenant_isolation
def test_activity_member_names_come_from_own_tenant(two_tenants) -> None:
    client, a, b = two_tenants
    client.put("/api/me", headers=a, json={"display_name": "Alice"})
    client.post(f"/api/leads/{CID}/attempts", headers=b, json={"channel": "call"})

    # B's activity rows are attributed by B's roster — A's display name
    # never bleeds into B's member-name lookups.
    b_events = client.get("/api/activity", headers=b).json()["events"]
    assert [e["member_name"] for e in b_events] == ["user-b"]
