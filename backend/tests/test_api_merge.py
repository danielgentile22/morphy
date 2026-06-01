"""Manual merge/split over HTTP — the Slice 7 (#53) endpoints through the real
stack (TestClient + a real session JWT), proving coalesce is honored end-to-end.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ._helpers import api, auth_header, login

A = "aaaaaaaaaaaa"
B = "bbbbbbbbbbbb"


def _owner(cid: str, name: str, states: list[str]) -> dict:
    return {
        "display_cluster_id": cid,
        "owner_name": name,
        "owner_name_norm": name,
        "owner_kind": "llc",
        "states": states,
        "n_states": len(states),
        "cross_state": len(states) >= 2,
        "parcel_count": 2,
        "tower_count": 3,
        "solar_count": 0,
        "total_assessed_value": 100.0,
        "max_parcel_score": 0.8,
        "score": 0.8,
        "distress_tier": "at-risk",
        "in_oz": False,
        "in_qct": False,
        "persistent_poverty": False,
    }


SAMPLE = {
    "schema_version": 3,
    "alpha": 0.1,
    "count": 2,
    "owners": [
        _owner(A, "AMERICAN TOWERS LLC", ["AR", "WV"]),
        _owner(B, "AMERICAN TOWER CORP", ["FL"]),
    ],
}


@pytest.fixture
def client() -> TestClient:
    with api(SAMPLE) as (c, _eng, _sender):
        c.headers.update(auth_header(login(c)))
        yield c


def test_merge_then_clusters_resolve_to_one_everywhere(client: TestClient) -> None:
    assert client.get("/api/candidates").json()["count"] == 2

    r = client.post(f"/api/leads/{A}/merge", json={"source_cluster_id": B})
    assert r.status_code == 200
    merged = r.json()
    assert merged["owner"]["display_cluster_id"] == A
    assert set(merged["owner"]["states"]) == {"AR", "FL", "WV"}  # combined rollup
    assert [mm["display_cluster_id"] for mm in merged["merged_members"]] == [B]

    # Candidates now lists one merged owner, not two.
    cands = client.get("/api/candidates").json()
    assert cands["count"] == 1
    assert cands["candidates"][0]["display_cluster_id"] == A

    # The merged-away source id resolves to the surviving Lead (map tower click).
    via_source = client.get(f"/api/leads/{B}").json()
    assert via_source["owner"]["display_cluster_id"] == A


def test_split_reverses_the_merge(client: TestClient) -> None:
    client.post(f"/api/leads/{A}/merge", json={"source_cluster_id": B})
    assert client.get("/api/candidates").json()["count"] == 1

    r = client.post(f"/api/leads/{A}/split", json={"source_cluster_id": B})
    assert r.status_code == 200
    assert r.json()["merged_members"] == []

    cands = client.get("/api/candidates").json()
    assert cands["count"] == 2  # both distinct again
    assert client.get(f"/api/leads/{B}").json()["owner"]["display_cluster_id"] == B


def test_merge_unknown_source_is_404(client: TestClient) -> None:
    assert (
        client.post(f"/api/leads/{A}/merge", json={"source_cluster_id": "nope"}).status_code == 404
    )


def test_merge_into_self_is_409(client: TestClient) -> None:
    r = client.post(f"/api/leads/{A}/merge", json={"source_cluster_id": A})
    assert r.status_code == 409


def test_split_with_no_override_is_404(client: TestClient) -> None:
    assert client.post(f"/api/leads/{A}/split", json={"source_cluster_id": B}).status_code == 404


def test_merge_endpoints_require_auth(client: TestClient) -> None:
    # Drop the bearer header → the override endpoints reject like every data route.
    assert (
        client.post(
            f"/api/leads/{A}/merge", json={"source_cluster_id": B}, headers={"Authorization": ""}
        ).status_code
        == 401
    )
