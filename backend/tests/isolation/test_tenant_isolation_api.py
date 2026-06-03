"""Route-level multi-tenancy isolation — the ADR-055 Day-1 requirement,
driven through real auth (Slice 2 / #48).

Two synthetic tenants, each authenticated with its *own* session JWT
(tenant A auto-provisioned into the default tenant; tenant B provisioned
into tenant 2). Every data route asserts "tenant A cannot read / write /
list tenant B's data" — even though only one tenant exists in production.
The store-level twin of these checks lives in ``test_tenant_isolation.py``.

Run with ``pytest -k tenant_isolation``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.auth import Principal, create_access_token

from .._helpers import api, auth_header

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
    """A client plus per-tenant auth headers for two distinct tenants.

    The two JWTs are minted directly via the seam (synthetic tenants 1 and 2,
    bypassing login + team registration) — the routes resolve the tenant from
    the token, which is exactly the isolation under test. The login-driven
    twin of these checks (real teams from the credentials file) lives in
    ``test_teams.py``.
    """
    with api(SAMPLE) as (client, _eng, _sender):
        header_a = auth_header(
            create_access_token(Principal(tenant_id=1, user_id=1, email="tenant-a"))
        )
        header_b = auth_header(
            create_access_token(Principal(tenant_id=2, user_id=2, email="tenant-b"))
        )
        yield client, header_a, header_b


@pytest.mark.tenant_isolation
def test_jwts_resolve_to_distinct_tenants(two_tenants) -> None:
    client, a, b = two_tenants
    assert client.get("/api/auth/me", headers=a).json()["tenant_id"] == 1
    assert client.get("/api/auth/me", headers=b).json()["tenant_id"] == 2


@pytest.mark.tenant_isolation
def test_b_cannot_read_a_lead_state(two_tenants) -> None:
    client, a, b = two_tenants
    client.put(f"/api/leads/{CID}", headers=a, json={"status": "researching", "notes": "A only"})

    b_view = client.get(f"/api/leads/{CID}", headers=b).json()
    assert b_view["status"] == "new"  # B sees the default, not A's advance
    assert b_view["notes"] == ""  # B never sees A's private note
    assert b_view["attempts"] == []  # nor A's auto-logged status row


@pytest.mark.tenant_isolation
def test_b_write_does_not_leak_into_a(two_tenants) -> None:
    client, a, b = two_tenants
    client.put(f"/api/leads/{CID}", headers=a, json={"status": "researching"})
    client.put(f"/api/leads/{CID}", headers=b, json={"status": "researching"})
    client.put(f"/api/leads/{CID}", headers=b, json={"status": "contacted"})  # B advances past A

    a_view = client.get(f"/api/leads/{CID}", headers=a).json()
    assert a_view["status"] == "researching"  # A untouched by B's writes


@pytest.mark.tenant_isolation
def test_candidates_list_is_per_tenant(two_tenants) -> None:
    client, a, b = two_tenants
    # A advances the owner off New → it leaves A's Candidates...
    client.put(f"/api/leads/{CID}", headers=a, json={"status": "researching"})
    a_ids = [
        c["display_cluster_id"]
        for c in client.get("/api/candidates", headers=a).json()["candidates"]
    ]
    b_ids = [
        c["display_cluster_id"]
        for c in client.get("/api/candidates", headers=b).json()["candidates"]
    ]
    assert CID not in a_ids  # ...but is still New for B, so still B's candidate
    assert CID in b_ids


@pytest.mark.tenant_isolation
def test_my_leads_board_and_counts_are_per_tenant(two_tenants) -> None:
    client, a, b = two_tenants
    # A advances the owner off New → onto A's kanban board only.
    client.put(f"/api/leads/{CID}", headers=a, json={"status": "researching"})

    a_board = client.get("/api/my-leads", headers=a).json()
    b_board = client.get("/api/my-leads", headers=b).json()
    assert [le["display_cluster_id"] for le in a_board["leads"]] == [CID]
    assert b_board["leads"] == []  # B never sees A's advanced lead

    # Nav counts are likewise scoped: the same owner is a My-Lead for A but
    # still a Candidate for B.
    assert client.get("/api/counts", headers=a).json() == {"candidates": 0, "my_leads": 1}
    assert client.get("/api/counts", headers=b).json() == {"candidates": 1, "my_leads": 0}


@pytest.mark.tenant_isolation
def test_unauthenticated_request_is_rejected(two_tenants) -> None:
    client, _a, _b = two_tenants
    assert client.get("/api/candidates").status_code == 401
    assert client.get("/api/my-leads").status_code == 401
    assert client.get("/api/counts").status_code == 401
    assert client.put(f"/api/leads/{CID}", json={"status": "researching"}).status_code == 401
