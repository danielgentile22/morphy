"""Full Lead page API (Slice 3 / #49) — driven over HTTP with a real JWT.

Exercises the read half (holdings + mailing + tallest tower in the detail
payload) and the write half (editable contact fields persist; a manual
contact attempt is logged; a status change auto-logs into the same stream).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ._helpers import api, auth_header, login

CID = "nat0000aaaa"
SAMPLE = {
    "schema_version": 2,
    "count": 1,
    "owners": [
        {
            "display_cluster_id": CID,
            "owner_name": "AMERICAN TOWERS LLC",
            "owner_name_norm": "AMERICAN TOWERS",
            "owner_kind": "llc",
            "states": ["AR", "WV"],
            "n_states": 2,
            "cross_state": True,
            "parcel_count": 2,
            "tower_count": 3,
            "solar_count": 1,
            "total_assessed_value": 150.0,
            "max_parcel_score": 0.9,
            "score": 0.97,
            "distress_tier": "distressed",
            "in_oz": True,
            "in_qct": True,
            "persistent_poverty": False,
            "tallest_tower_height_m": 120.0,
            "mailing_address": {
                "addr": "10 MAIN ST",
                "city": "BOSTON",
                "state": "MA",
                "zip": "02101",
            },
            "holdings": [
                {
                    "parcel_id": "P1",
                    "state": "AR",
                    "county_fips": "05123",
                    "land_use": "AV",
                    "assessed_value": 100.0,
                    "acreage": 10.5,
                    "tower_count": 2,
                    "solar_count": 0,
                    "bbox": [-90.4, 35.0, -90.41, 35.05],
                    "point": [-90.405, 35.025],
                    "structures": [
                        {
                            "type": "tower",
                            "asr": "A1",
                            "height_m": 120.0,
                            "lat": 35.02,
                            "lon": -90.4,
                            "active": True,
                            "structure_kind": "TOWER",
                            "score": 0.91,
                            "carriers": [
                                {
                                    "carrier_name": "AT&T",
                                    "callsign": "KNKN566",
                                    "license_expiry": "2031-10-01",
                                    "confidence_tag": "verified",
                                }
                            ],
                        }
                    ],
                },
                {
                    "parcel_id": "P2",
                    "state": "WV",
                    "county_fips": "54001",
                    "land_use": "RV",
                    "assessed_value": 50.0,
                    "acreage": 3.0,
                    "tower_count": 1,
                    "solar_count": 1,
                    "bbox": [-81.0, 38.0, -81.01, 38.02],
                    "point": [-81.005, 38.01],
                    "structures": [{"type": "solar", "id": "S1", "owner": "Acme Solar"}],
                },
            ],
        }
    ],
}


@pytest.fixture
def client() -> TestClient:
    with api(SAMPLE) as (c, _eng, _sender):
        c.headers.update(auth_header(login(c)))
        yield c


def test_lead_detail_includes_holdings_mailing_and_tallest(client: TestClient) -> None:
    body = client.get(f"/api/leads/{CID}").json()
    assert body["tallest_tower_height_m"] == 120.0
    assert body["mailing_address"]["city"] == "BOSTON"
    assert len(body["holdings"]) == 2
    assert {h["state"] for h in body["holdings"]} == {"AR", "WV"}
    # the AR holding's tower structure carries height + EPSG:4326 geometry
    ar = next(h for h in body["holdings"] if h["state"] == "AR")
    assert ar["structures"][0]["height_m"] == 120.0
    assert ar["point"] == [-90.405, 35.025]
    # per-tower score (#105) survives the response_model boundary — an
    # undeclared field would be silently dropped here.
    assert ar["structures"][0]["score"] == 0.91
    # carriers (Slice A / #28) survive the response_model boundary — a field
    # absent from the Structure schema would be silently dropped here.
    carriers = ar["structures"][0]["carriers"]
    assert len(carriers) == 1
    assert (carriers[0]["carrier_name"], carriers[0]["confidence_tag"]) == ("AT&T", "verified")
    # the WV holding's solar structure has no carriers → empty list, not absent
    wv = next(h for h in body["holdings"] if h["state"] == "WV")
    assert wv["structures"][0]["carriers"] == []


def test_contact_fields_persist_via_put_and_reload(client: TestClient) -> None:
    put = client.put(
        f"/api/leads/{CID}",
        json={
            "contact_name": "Jane Roe",
            "contact_phone": "555-0100",
            "contact_email": "jane@example.com",
            "best_channel": "phone",
        },
    )
    assert put.status_code == 200
    assert put.json()["contact_name"] == "Jane Roe"

    again = client.get(f"/api/leads/{CID}").json()
    assert again["contact_phone"] == "555-0100"
    assert again["best_channel"] == "phone"
    # editing contact info is not a status change → no auto-logged row
    assert again["attempts"] == []


def test_log_contact_attempt_appears_in_the_stream(client: TestClient) -> None:
    r = client.post(
        f"/api/leads/{CID}/attempts",
        json={"channel": "phone", "outcome": "left voicemail", "occurred_on": "2026-05-30"},
    )
    assert r.status_code == 200
    attempts = r.json()["attempts"]
    assert len(attempts) == 1
    assert (attempts[0]["channel"], attempts[0]["outcome"]) == ("phone", "left voicemail")
    assert attempts[0]["occurred_on"] == "2026-05-30"


def test_outbound_attempt_defaults_direction_through_response_model(client: TestClient) -> None:
    # A touch with no direction round-trips as outbound — guards the
    # ContactAttemptOut.direction declaration (an undeclared field would be
    # silently dropped by response_model).
    r = client.post(f"/api/leads/{CID}/attempts", json={"channel": "phone", "outcome": "x"})
    assert r.status_code == 200
    assert r.json()["attempts"][0]["direction"] == "outbound"


def test_log_reply_is_inbound_and_does_not_change_status(client: TestClient) -> None:
    r = client.post(
        f"/api/leads/{CID}/attempts",
        json={"channel": "email", "outcome": "interested", "direction": "inbound"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["attempts"][0]["direction"] == "inbound"
    # logging a reply never advances the Lead's status (#106 / ADR-066)
    assert body["status"] == "new"


def test_attempt_rejects_a_bad_direction(client: TestClient) -> None:
    r = client.post(
        f"/api/leads/{CID}/attempts",
        json={"channel": "email", "outcome": "x", "direction": "sideways"},
    )
    assert r.status_code == 422


def test_status_change_and_manual_attempt_share_one_stream(client: TestClient) -> None:
    client.put(f"/api/leads/{CID}", json={"status": "researching"})  # auto-logs
    client.post(f"/api/leads/{CID}/attempts", json={"channel": "mail", "outcome": "sent"})
    channels = {a["channel"] for a in client.get(f"/api/leads/{CID}").json()["attempts"]}
    assert channels == {"status", "mail"}


def test_attempt_requires_a_channel(client: TestClient) -> None:
    assert (
        client.post(f"/api/leads/{CID}/attempts", json={"channel": "", "outcome": "x"}).status_code
        == 422
    )


def test_attempt_rejects_a_bad_date(client: TestClient) -> None:
    r = client.post(
        f"/api/leads/{CID}/attempts",
        json={"channel": "phone", "outcome": "x", "occurred_on": "not-a-date"},
    )
    assert r.status_code == 422


def test_attempt_on_unknown_owner_is_404(client: TestClient) -> None:
    assert client.post("/api/leads/nope/attempts", json={"channel": "phone"}).status_code == 404
