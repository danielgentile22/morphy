"""End-to-end API smoke test — the tracer spine through the real stack.

Drives the FastAPI app over HTTP (TestClient) against a tiny owners index
and a fresh in-memory SQLite DB, authenticated with a real session JWT
(``login`` posts username/password to ``/api/auth/login``), proving:
candidates → open lead → set status + note → persists → reload reflects it,
and that an illegal transition is rejected.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ._helpers import api, auth_header, login

SAMPLE = {
    "schema_version": 1,
    "alpha": 0.1,
    "states": ["05", "54"],
    "count": 2,
    "owners": [
        {
            "display_cluster_id": "nat0000aaaa",
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
            "display_cluster_id": "loc0000bbbb",
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
def client() -> Iterator[TestClient]:
    # A fresh in-memory DB per test, authenticated with a real JWT so the
    # tracer runs exactly as the SPA does (the Bearer header is attached to
    # every request via the client's default headers).
    with api(SAMPLE) as (c, _eng, _sender):
        c.headers.update(auth_header(login(c)))
        yield c


def test_candidates_lists_owners_at_new_ranked(client: TestClient) -> None:
    body = client.get("/api/candidates").json()
    assert body["count"] == 2
    # ranked by score desc — the national tower-co first
    names = [c["owner_name"] for c in body["candidates"]]
    assert names == ["AMERICAN TOWERS LLC", "SMITH FAMILY TRUST"]
    assert body["candidates"][0]["cross_state"] is True
    assert body["candidates"][0]["status"] == "new"


def test_open_set_status_note_persists_and_reloads(client: TestClient) -> None:
    cid = "nat0000aaaa"
    assert client.get(f"/api/leads/{cid}").json()["status"] == "new"

    put = client.put(f"/api/leads/{cid}", json={"status": "researching", "notes": "called"})
    assert put.status_code == 200
    assert put.json()["status"] == "researching"

    # survives a "reload": fetch again
    again = client.get(f"/api/leads/{cid}").json()
    assert again["status"] == "researching"
    assert again["notes"] == "called"
    # the transition auto-logged an activity row
    assert any(a["channel"] == "status" for a in again["attempts"])

    # and it left the Candidates surface (no longer New)
    assert "nat0000aaaa" not in [
        c["display_cluster_id"] for c in client.get("/api/candidates").json()["candidates"]
    ]


def test_illegal_transition_returns_409(client: TestClient) -> None:
    r = client.put("/api/leads/nat0000aaaa", json={"status": "in_business"})
    assert r.status_code == 409
    assert "illegal transition" in r.json()["detail"]


def test_unknown_owner_is_404(client: TestClient) -> None:
    assert client.get("/api/leads/doesnotexist").status_code == 404
    assert client.put("/api/leads/doesnotexist", json={"status": "researching"}).status_code == 404
