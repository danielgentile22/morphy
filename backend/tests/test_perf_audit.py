"""Parity + invariant tests for the 2026-06-07 performance pass.

These guard the *behavior-preserving* refactors whose whole point is "same
output, less work": the get_owner single-owner fast path (PERF-009), the
O(persisted-leads) counts (PERF-005), the activity SQL-filter push-down
(PERF-008), the merged-member IN-query (PERF-022), the TaskStore EXISTS/DELETE
helpers (PERF-023), and the additive composite indexes (PERF-006 / PERF-023).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db import init_db
from backend.app.lead_store import LeadStore
from backend.app.owner_merge_service import OwnerMergeService
from backend.app.owners_index_service import OwnersIndexService
from backend.app.task_store import TaskStore


def _owner(cid: str, name: str, score: float, **extra) -> dict:
    base = {
        "display_cluster_id": cid,
        "owner_name": name,
        "owner_name_norm": name,
        "owner_kind": "llc",
        "states": ["AR"],
        "n_states": 1,
        "cross_state": False,
        "parcel_count": 1,
        "tower_count": 1,
        "solar_count": 0,
        "structure_count": 1,
        "active_tower_count": 1,
        "total_assessed_value": 100.0,
        "max_parcel_score": score,
        "score": score,
        "distress_tier": "at-risk",
        "in_oz": False,
        "in_qct": False,
        "persistent_poverty": False,
        "counties": ["05001"],
        "structure_types": ["tower"],
        "tallest_tower_height_m": 100.0,
        "mailing_address": {"addr": f"{cid} st"},
        "holdings": [{"parcel_id": f"{cid}-p", "state": "AR"}],
    }
    base.update(extra)
    return base


@pytest.fixture
def three_owner_service(tmp_path: Path) -> OwnersIndexService:
    sample = {
        "schema_version": 4,
        "count": 3,
        "alpha": 0.1,
        "owners": [
            _owner("aaa", "ALPHA LLC", 0.9, states=["AR"]),
            _owner("bbb", "BETA LLC", 0.7, states=["WV"]),
            _owner("ccc", "GAMMA LLC", 0.5, states=["MT"]),
        ],
    }
    path = tmp_path / "owners_index.json"
    path.write_text(json.dumps(sample))
    return OwnersIndexService(path)


# ── PERF-009: get_owner fast path is byte-identical to effective() ───────────
def test_get_owner_no_overrides_matches_effective(
    three_owner_service: OwnersIndexService, new_session: Callable[[], Session]
) -> None:
    svc = three_owner_service
    merges = OwnerMergeService(new_session(), 1)  # empty override map
    for cid in ("aaa", "bbb", "ccc"):
        _, by_id = svc.effective(merges)
        assert svc.get_owner(cid, merges) == by_id[cid]


def test_get_owner_fast_path_matches_effective_under_three_way_merge(
    three_owner_service: OwnersIndexService, new_session: Callable[[], Session]
) -> None:
    svc = three_owner_service
    merges = OwnerMergeService(new_session(), 1)
    merges.merge(source="bbb", target="aaa")
    merges.merge(source="ccc", target="aaa")  # all three resolve to aaa

    _, by_id = svc.effective(merges)
    merged = by_id["aaa"]
    # Every member id resolves to the same merged owner, byte-identical to the
    # list-path merge — including the concatenated holdings order.
    for cid in ("aaa", "bbb", "ccc"):
        assert svc.get_owner(cid, merges) == merged
    assert merged["holdings"] == [
        {"parcel_id": "aaa-p", "state": "AR"},
        {"parcel_id": "bbb-p", "state": "AR"},
        {"parcel_id": "ccc-p", "state": "AR"},
    ]
    assert set(merged["states"]) == {"AR", "WV", "MT"}


# ── PERF-005: counts == iterating effective owners, incl. an orphan lead ─────
def test_counts_match_owner_iteration_with_orphan_lead(
    three_owner_service: OwnersIndexService, store_factory: Callable[[int], LeadStore]
) -> None:
    svc = three_owner_service
    store = store_factory(1)
    store.upsert("aaa", status="researching")  # off New → my-lead
    store.upsert("bbb", status="researching")  # off New → my-lead
    store.upsert("orphan-not-in-index", status="researching")  # must NOT be counted

    got = svc.counts(store)
    # Reference: iterate the effective owners exactly as the old code did.
    owners, _ = svc.effective(None)
    status_map = store.status_map()
    my = sum(1 for o in owners if status_map.get(o["display_cluster_id"], "new") != "new")
    assert got == {"candidates": len(owners) - my, "my_leads": my}
    assert got == {"candidates": 1, "my_leads": 2}


# ── PERF-008: SQL-filtered activity stream matches a Python filter ───────────
def test_tenant_attempts_sql_filters_match_python(
    store_factory: Callable[[int], LeadStore],
) -> None:
    from datetime import date

    store = store_factory(1)
    store.append_attempt("aaa", channel="phone", occurred_on=date(2026, 6, 1), logged_by_user_id=1)
    store.append_attempt("aaa", channel="email", occurred_on=date(2026, 6, 5), logged_by_user_id=2)
    store.append_attempt("bbb", channel="phone", occurred_on=date(2026, 6, 3), logged_by_user_id=1)
    store.append_attempt(
        "aaa", channel="dismiss", occurred_on=date(2026, 6, 4), logged_by_user_id=1
    )

    full = store.tenant_attempts(exclude_channels=("dismiss",))
    # lead filter
    assert [a.id for a in store.tenant_attempts(lead="aaa", exclude_channels=("dismiss",))] == [
        a.id for a in full if a.display_cluster_id == "aaa"
    ]
    # member filter
    assert [a.id for a in store.tenant_attempts(member=1, exclude_channels=("dismiss",))] == [
        a.id for a in full if a.logged_by_user_id == 1
    ]
    # date window (inclusive)
    win = store.tenant_attempts(
        date_from=date(2026, 6, 2), date_to=date(2026, 6, 4), exclude_channels=("dismiss",)
    )
    assert [a.id for a in win] == [
        a.id for a in full if date(2026, 6, 2) <= a.occurred_on <= date(2026, 6, 4)
    ]
    # dismiss is excluded
    assert all(a.channel != "dismiss" for a in full)


# ── PERF-023: TaskStore EXISTS / bulk-cancel helpers ─────────────────────────
def test_task_has_open_and_cancel_open(store_factory: Callable[[int], LeadStore]) -> None:
    session = store_factory(1).session
    tasks = TaskStore(session, 1)
    tasks.create(title="chase", lead_cluster_id="aaa", source="auto")
    tasks.create(title="chase2", lead_cluster_id="aaa", source="auto", status="done")
    tasks.create(title="manual", lead_cluster_id="aaa", source="manual")

    assert tasks.has_open("aaa", "auto") is True
    assert tasks.has_open("bbb", "auto") is False
    # cancels only the open auto task (not the done one, not the manual one)
    assert tasks.cancel_open("aaa", "auto") == 1
    assert tasks.has_open("aaa", "auto") is False
    assert tasks.has_open("aaa", "manual") is True


# ── PERF-006 / PERF-023: the additive composite indexes exist after init_db ──
def test_added_composite_indexes_exist_after_init_db() -> None:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    init_db(eng)
    insp = inspect(eng)
    attempt_idx = {i["name"] for i in insp.get_indexes("contact_attempt")}
    task_idx = {i["name"] for i in insp.get_indexes("task")}
    assert {"ix_attempt_tenant_occurred", "ix_attempt_tenant_cid_occurred"} <= attempt_idx
    assert "ix_task_tenant_created" in task_idx
