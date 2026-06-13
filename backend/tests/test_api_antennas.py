"""Per-antenna manual-state routes over HTTP (UI overhaul round 2).

``GET/PUT /api/antennas/{asr}`` is the editable layer over a single antenna —
an address, an archived flag, and manual owner details for a tower whose
landowner we couldn't auto-resolve. ``GET /api/antennas/archived`` is the set
the Explore map + list exclude by default.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ._helpers import api, auth_header, login

# A minimal owners index — the antenna routes don't read it, but ``api`` needs one.
SAMPLE = {"schema_version": 1, "count": 0, "owners": []}

ASR = "1287345"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with api(SAMPLE) as (c, _eng, _sender):
        c.headers.update(auth_header(login(c)))
        yield c


def test_unedited_antenna_returns_empty_state(client: TestClient) -> None:
    s = client.get(f"/api/antennas/{ASR}").json()
    assert s == {
        "asr": ASR,
        "archived": False,
        "address": "",
        "owner_name": "",
        "owner_phone": "",
        "owner_email": "",
        "notes": "",
    }


def test_put_address_and_manual_owner_details_persist(client: TestClient) -> None:
    client.put(
        f"/api/antennas/{ASR}",
        json={
            "address": "300 Tower Rd, Pulaski Co, AR",
            "owner_name": "Smith Family Trust",
            "owner_phone": "555-0142",
            "owner_email": "trust@example.com",
            "notes": "no parcel match — owner from county deed search",
        },
    )
    s = client.get(f"/api/antennas/{ASR}").json()
    assert s["address"] == "300 Tower Rd, Pulaski Co, AR"
    assert s["owner_name"] == "Smith Family Trust"
    assert s["owner_phone"] == "555-0142"
    assert s["owner_email"] == "trust@example.com"
    assert s["notes"] == "no parcel match — owner from county deed search"
    assert s["archived"] is False


def test_archive_then_recover_via_archived_list(client: TestClient) -> None:
    assert client.get("/api/antennas/archived").json()["asrs"] == []
    client.put(f"/api/antennas/{ASR}", json={"archived": True})
    assert client.get("/api/antennas/archived").json()["asrs"] == [ASR]
    # recoverable: un-archiving drops it from the list
    client.put(f"/api/antennas/{ASR}", json={"archived": False})
    assert client.get("/api/antennas/archived").json()["asrs"] == []


def test_partial_put_does_not_clobber_other_fields(client: TestClient) -> None:
    client.put(f"/api/antennas/{ASR}", json={"address": "kept address"})
    client.put(f"/api/antennas/{ASR}", json={"archived": True})  # archive only
    s = client.get(f"/api/antennas/{ASR}").json()
    assert s["archived"] is True
    assert s["address"] == "kept address"  # archiving didn't wipe the address


def test_archived_route_is_literal_not_an_asr(client: TestClient) -> None:
    # The /archived path must resolve to the list route, never be treated as an
    # antenna with asr="archived".
    body = client.get("/api/antennas/archived").json()
    assert "asrs" in body and "asr" not in body


def test_antenna_routes_require_auth(client: TestClient) -> None:
    naked = TestClient(client.app)
    assert naked.get(f"/api/antennas/{ASR}").status_code == 401
    assert naked.get("/api/antennas/archived").status_code == 401
    assert naked.put(f"/api/antennas/{ASR}", json={"archived": True}).status_code == 401
