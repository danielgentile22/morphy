"""Multi-tenancy isolation — the ADR-055 Day-1 requirement.

Even with a single real tenant in production, the schema is tenant-shaped
and every read/write filters by ``tenant_id``. These tests prove a second
tenant's writes are invisible across the boundary, so adding a tenant is a
row-add, not a refactor.

Run with ``pytest -k tenant_isolation``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from backend.app.lead_store import LeadStore

CID = "owner0000aaaa"
TENANT_A = 1
TENANT_B = 2


@pytest.mark.tenant_isolation
def test_tenant_b_cannot_read_tenant_a_lead(
    store_factory: Callable[[int], LeadStore],
) -> None:
    store_factory(TENANT_A).upsert(CID, status="researching", notes="A's private note")

    b = store_factory(TENANT_B)
    assert b.get_lead(CID) is None
    assert b.list_leads() == []
    assert b.status_map() == {}


@pytest.mark.tenant_isolation
def test_tenant_b_cannot_read_tenant_a_attempts(
    store_factory: Callable[[int], LeadStore],
) -> None:
    # The auto-logged status row belongs to tenant A only.
    store_factory(TENANT_A).upsert(CID, status="researching")
    assert store_factory(TENANT_B).list_attempts(CID) == []
    assert len(store_factory(TENANT_A).list_attempts(CID)) == 1


@pytest.mark.tenant_isolation
def test_same_cluster_id_is_independent_per_tenant(
    store_factory: Callable[[int], LeadStore],
) -> None:
    # Both tenants work the *same* landowner cluster id; their lead state
    # must not collide (the PK is (tenant_id, display_cluster_id)).
    store_factory(TENANT_A).upsert(CID, status="researching", notes="A")
    b = store_factory(TENANT_B)
    b.upsert(CID, status="researching")
    b.upsert(CID, status="uninterested", notes="B")  # legal ladder walk

    a = store_factory(TENANT_A).get_lead(CID)
    b_lead = store_factory(TENANT_B).get_lead(CID)
    assert (a.status, a.notes) == ("researching", "A")
    assert (b_lead.status, b_lead.notes) == ("uninterested", "B")


@pytest.mark.tenant_isolation
def test_tenant_b_write_does_not_leak_into_tenant_a(
    store_factory: Callable[[int], LeadStore],
) -> None:
    store_factory(TENANT_A).upsert(CID, status="researching")
    b = store_factory(TENANT_B)
    b.upsert(CID, status="researching")
    b.upsert(CID, status="contacted")  # B advances past A

    # A's lead is untouched by B's write.
    assert store_factory(TENANT_A).get_lead(CID).status == "researching"
