"""My-Leads kanban surface over HTTP (Slice 5 / #51).

Exercises the two new reads — ``GET /api/my-leads`` (the worklist) and
``GET /api/counts`` (the nav badges) — plus the drag-driven status change,
which reuses ``PUT /api/leads/{id}``: a legal move persists + auto-logs an
activity row; an illegal move is rejected server-side (the client reverts
the card). Authenticated with a real magic-link JWT, like the SPA.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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


def test_board_is_empty_and_counts_all_candidates_before_any_work(client: TestClient) -> None:
    assert client.get("/api/my-leads").json() == {"count": 0, "leads": []}
    assert client.get("/api/counts").json() == {"candidates": 2, "my_leads": 0}


def test_advancing_off_new_moves_owner_onto_the_board(client: TestClient) -> None:
    client.put(f"/api/leads/{NAT}", json={"status": "researching"})

    board = client.get("/api/my-leads").json()
    assert board["count"] == 1
    assert board["leads"][0]["display_cluster_id"] == NAT
    assert board["leads"][0]["status"] == "researching"  # lane bucket
    # The New owner is absent from the board (it stays in Candidates).
    assert LOC not in [le["display_cluster_id"] for le in board["leads"]]

    assert client.get("/api/counts").json() == {"candidates": 1, "my_leads": 1}


def test_legal_drag_persists_and_autologs_activity(client: TestClient) -> None:
    # Drag New→Researching, then Researching→Contacted (two legal lane moves).
    client.put(f"/api/leads/{NAT}", json={"status": "researching"})
    moved = client.put(f"/api/leads/{NAT}", json={"status": "contacted"})
    assert moved.status_code == 200
    assert moved.json()["status"] == "contacted"

    # The card now sits in the Contacted lane after a reload.
    board = client.get("/api/my-leads").json()
    assert board["leads"][0]["status"] == "contacted"
    # Both transitions were auto-logged into the activity stream.
    status_rows = [a for a in moved.json()["attempts"] if a["channel"] == "status"]
    assert {r["outcome"] for r in status_rows} == {"new→researching", "researching→contacted"}


def test_illegal_drag_is_rejected_and_card_stays_put(client: TestClient) -> None:
    client.put(f"/api/leads/{NAT}", json={"status": "researching"})
    # Dropping a Researching card straight into In Business skips Contacted +
    # Interested — illegal. The server (authoritative) rejects it with 409.
    bad = client.put(f"/api/leads/{NAT}", json={"status": "in_business"})
    assert bad.status_code == 409
    assert "illegal transition" in bad.json()["detail"]

    # The Lead is unchanged — the client reverts the optimistic move.
    board = client.get("/api/my-leads").json()
    assert board["leads"][0]["status"] == "researching"
    assert client.get("/api/counts").json() == {"candidates": 1, "my_leads": 1}


def test_kanban_reads_require_auth(client: TestClient) -> None:
    # A bare client (no Bearer header) is rejected on both new reads.
    naked = TestClient(client.app)
    assert naked.get("/api/my-leads").status_code == 401
    assert naked.get("/api/counts").status_code == 401
