"""Pursue: Explore → Leads handoff + trigger capture (UI overhaul P1 / #109,
ADR-067/D2). Store-level + API-level. The trigger is a ``channel='flag'``
activity row (no schema change), surfaced as ``OwnerSummary.trigger_asr``."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.lead_store import LeadStore
from backend.app.owners_index_service import OwnersIndexService

from ._helpers import api, auth_header, login

CID = "21cbe4dd35d5"
OTHER = "ffff0000bbbb"


# ── store level ───────────────────────────────────────────────────────────────
def test_pursue_advances_new_to_researching(store_factory: Callable[[int], LeadStore]) -> None:
    lead = store_factory(1).pursue(CID, trigger_asr="1287345")
    assert lead.status == "researching"
    reloaded = store_factory(1).get_lead(CID)
    assert reloaded.status == "researching"


def test_pursue_records_the_trigger_flag(store_factory: Callable[[int], LeadStore]) -> None:
    store_factory(1).pursue(CID, trigger_asr="1287345")
    flags = store_factory(1).latest_flags()
    assert flags.get(CID) == "1287345"
    # the status transition + the flag are both in the activity stream
    channels = {a.channel for a in store_factory(1).list_attempts(CID)}
    assert {"status", "flag"} <= channels


def test_pursue_keeps_latest_trigger(store_factory: Callable[[int], LeadStore]) -> None:
    store = store_factory(1)
    store.pursue(CID, trigger_asr="111")
    store.pursue(CID, trigger_asr="222")  # already off New → just another trigger
    assert store_factory(1).latest_flags().get(CID) == "222"
    # second pursue did not illegally re-advance status
    assert store_factory(1).get_lead(CID).status == "researching"


def test_pursue_without_trigger_still_advances(store_factory: Callable[[int], LeadStore]) -> None:
    store_factory(1).pursue(CID)
    assert store_factory(1).get_lead(CID).status == "researching"
    assert store_factory(1).latest_flags() == {}


def test_triggers_are_tenant_scoped(store_factory: Callable[[int], LeadStore]) -> None:
    store_factory(1).pursue(CID, trigger_asr="111")
    assert store_factory(2).latest_flags() == {}


# ── service level: trigger surfaces on the worklist + lead view ──────────────
_SAMPLE = {
    "schema_version": 5,
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
            "tower_count": 1,
            "solar_count": 0,
            "total_assessed_value": 100.0,
            "max_parcel_score": 0.9,
            "score": 0.9,
            "distress_tier": "distressed",
            "in_oz": False,
            "in_qct": False,
            "persistent_poverty": False,
            "holdings": [],
        }
    ],
}


def test_my_leads_carries_the_trigger(
    tmp_path: Path, store_factory: Callable[[int], LeadStore]
) -> None:
    path = tmp_path / "idx.json"
    path.write_text(json.dumps(_SAMPLE))
    svc = OwnersIndexService(path)
    store_factory(1).pursue(CID, trigger_asr="1287345")
    rows = svc.list_my_leads(store_factory(1))
    assert len(rows) == 1
    assert rows[0]["trigger_asr"] == "1287345"


def test_lead_view_surfaces_the_trigger(
    tmp_path: Path, store_factory: Callable[[int], LeadStore]
) -> None:
    path = tmp_path / "idx.json"
    path.write_text(json.dumps(_SAMPLE))
    svc = OwnersIndexService(path)
    store_factory(1).pursue(CID, trigger_asr="1287345")
    view = svc.lead_view(store_factory(1), CID)
    assert view["owner"]["trigger_asr"] == "1287345"


# ── API level ─────────────────────────────────────────────────────────────────
@pytest.fixture
def client() -> TestClient:
    with api(_SAMPLE) as (c, _eng, _sender):
        c.headers.update(auth_header(login(c)))
        yield c


def test_pursue_endpoint_advances_and_records_trigger(client: TestClient) -> None:
    r = client.post(f"/api/leads/{CID}/pursue", json={"trigger_asr": "1287345"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "researching"
    assert body["owner"]["trigger_asr"] == "1287345"
    # it now appears on the My-Leads worklist with its trigger
    leads = client.get("/api/my-leads").json()["leads"]
    assert any(o["display_cluster_id"] == CID and o["trigger_asr"] == "1287345" for o in leads)


def test_pursue_unknown_owner_is_404(client: TestClient) -> None:
    assert client.post(f"/api/leads/{OTHER}/pursue", json={"trigger_asr": "1"}).status_code == 404
