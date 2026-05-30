"""OwnersIndexService.lead_view — serves the static owners index (rollups +
holdings + mailing address) left-joined with the tenant's editable lead
state (status, notes, contact fields, attempts). Synthetic owner data only.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from backend.app.lead_store import LeadStore
from backend.app.owners_index_service import OwnersIndexService

# A cross-state owner with two holdings (one tower-bearing, one solar) and a
# read-only mailing address — the v2 index shape the precompute emits.
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
                    "structures": [
                        {"type": "solar", "id": "S1", "owner": "Acme Solar"},
                    ],
                },
            ],
        }
    ],
}


@pytest.fixture
def service(tmp_path: Path) -> OwnersIndexService:
    path = tmp_path / "owners_index.json"
    path.write_text(json.dumps(SAMPLE))
    return OwnersIndexService(path)


def test_lead_view_returns_holdings_across_states(
    service: OwnersIndexService, store_factory: Callable[[int], LeadStore]
) -> None:
    view = service.lead_view(store_factory(1), CID)
    assert view is not None
    holdings = view["holdings"]
    assert {h["state"] for h in holdings} == {"AR", "WV"}
    assert len(holdings) == 2
    # tallest tower + read-only mailing come through from the static index
    assert view["tallest_tower_height_m"] == 120.0
    assert view["mailing_address"]["city"] == "BOSTON"


def test_lead_view_defaults_lead_state_when_no_lead_yet(
    service: OwnersIndexService, store_factory: Callable[[int], LeadStore]
) -> None:
    view = service.lead_view(store_factory(1), CID)
    assert view["status"] == "new"
    assert view["notes"] == ""
    assert view["contact_name"] == ""
    assert view["attempts"] == []


def test_lead_view_joins_editable_contact_state(
    service: OwnersIndexService, store_factory: Callable[[int], LeadStore]
) -> None:
    store_factory(1).upsert(
        CID,
        status="researching",
        notes="cross-state portfolio",
        contact={"contact_name": "Jane Roe", "best_channel": "phone"},
    )
    view = service.lead_view(store_factory(1), CID)
    assert view["status"] == "researching"
    assert view["notes"] == "cross-state portfolio"
    assert view["contact_name"] == "Jane Roe"
    assert view["best_channel"] == "phone"
    # the status transition auto-logged into the same stream
    assert any(a["channel"] == "status" for a in view["attempts"])


def test_lead_view_holdings_are_per_tenant_independent(
    service: OwnersIndexService, store_factory: Callable[[int], LeadStore]
) -> None:
    # Static holdings are shared, but the joined lead state is tenant-scoped:
    # tenant 2 sees the same holdings but its own (default) lead state.
    store_factory(1).upsert(CID, notes="tenant-1 only")
    view_b = service.lead_view(store_factory(2), CID)
    assert len(view_b["holdings"]) == 2  # holdings visible to both
    assert view_b["notes"] == ""  # but tenant 1's note is not


def test_unknown_owner_yields_none(
    service: OwnersIndexService, store_factory: Callable[[int], LeadStore]
) -> None:
    assert service.lead_view(store_factory(1), "doesnotexist") is None


def test_pre_v2_index_without_holdings_degrades_safely(
    tmp_path: Path, store_factory: Callable[[int], LeadStore]
) -> None:
    legacy = {
        "schema_version": 1,
        "count": 1,
        "owners": [{**SAMPLE["owners"][0]}],
    }
    # Strip the v2-only keys to simulate an index built before this slice.
    for key in ("holdings", "mailing_address", "tallest_tower_height_m"):
        legacy["owners"][0].pop(key, None)
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy))
    view = OwnersIndexService(path).lead_view(store_factory(1), CID)
    assert view["holdings"] == []
    assert view["mailing_address"] is None
    assert view["tallest_tower_height_m"] is None
