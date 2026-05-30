"""OwnerMergeService + the override-aware read path (Slice 7 / #53, ADR-056).

Maps directly to #53's acceptance criteria, on synthetic owner data:

  - merging two clusters makes them resolve to one ``display_cluster_id``;
  - ``coalesce(override_target, raw_cluster_id)`` is honored on the served index
    (Candidates / counts / Lead view) and on the merged rollups;
  - split reverses it;
  - overrides survive an owners-index recompute with raw parquet ids unchanged;
  - overrides are tenant-scoped (tenant A's merge is invisible to tenant B);
  - the target-wins / streams-concatenate lead-state reconciliation rule.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from backend.app.lead_store import LeadStore
from backend.app.owner_merge_service import MergeError, OwnerMergeService
from backend.app.owners_index_service import OwnersIndexService

# Two distinct national tower-cos the conservative resolver kept apart, plus a
# third unrelated owner. AMERICAN TOWERS vs AMERICAN TOWER are the merge target.
A = "aaaaaaaaaaaa"  # AMERICAN TOWERS LLC  (AR, WV)
B = "bbbbbbbbbbbb"  # AMERICAN TOWER CORP  (FL)
C = "cccccccccccc"  # SMITH FAMILY TRUST   (AR) — never touched


def _owner(cid: str, name: str, states: list[str], **over) -> dict:
    base = {
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
        "max_parcel_score": 0.5,
        "score": 0.5,
        "distress_tier": "at-risk",
        "in_oz": False,
        "in_qct": False,
        "persistent_poverty": False,
        "counties": [f"{states[0]}001"],
        "structure_count": 3,
        "structure_types": ["tower"],
        "active_tower_count": 1,
        "tallest_tower_height_m": 100.0,
        "mailing_address": {"addr": "1 A ST", "city": "X", "state": states[0], "zip": "1"},
        "holdings": [{"parcel_id": f"{cid}-p1", "state": states[0]}],
    }
    base.update(over)
    return base


SAMPLE = {
    "schema_version": 3,
    "alpha": 0.1,
    "count": 3,
    "owners": [
        _owner(A, "AMERICAN TOWERS LLC", ["AR", "WV"], max_parcel_score=0.9, score=0.97),
        _owner(B, "AMERICAN TOWER CORP", ["FL"], distress_tier="distressed", in_oz=True),
        _owner(C, "SMITH FAMILY TRUST", ["AR"], owner_kind="trust"),
    ],
}


@pytest.fixture
def service(tmp_path: Path) -> OwnersIndexService:
    path = tmp_path / "owners_index.json"
    path.write_text(json.dumps(SAMPLE))
    return OwnersIndexService(path)


def _merges(store_factory: Callable[[int], LeadStore], tenant: int) -> OwnerMergeService:
    # Reuse the LeadStore session so writes + reads are one transaction.
    store = store_factory(tenant)
    return OwnerMergeService(store.session, tenant)


# ── resolve = coalesce(override_target, raw_cluster_id) ──────────────────────
def test_resolve_is_identity_without_override(store_factory) -> None:
    m = _merges(store_factory, 1)
    assert m.resolve(A) == A
    assert m.override_map() == {}


def test_merge_makes_source_resolve_to_target(store_factory) -> None:
    m = _merges(store_factory, 1)
    m.merge(source=B, target=A)
    assert m.resolve(B) == A  # coalesce → target
    assert m.resolve(A) == A  # target unchanged
    assert m.members_of(A) == {A, B}


def test_split_returns_source_to_raw_cluster(store_factory) -> None:
    m = _merges(store_factory, 1)
    m.merge(source=B, target=A)
    assert m.split(source=B) is True
    assert m.resolve(B) == B  # back to its raw cluster
    assert m.members_of(A) == {A}
    assert m.split(source=B) is False  # idempotent: nothing left to split


def test_merge_chain_resolves_to_root(store_factory) -> None:
    # C→B then B→A : C must resolve all the way to A (coalesce over the chain).
    m = _merges(store_factory, 1)
    m.merge(source=C, target=B)
    m.merge(source=B, target=A)
    assert m.resolve(C) == A
    assert m.members_of(A) == {A, B, C}


def test_self_merge_is_rejected(store_factory) -> None:
    m = _merges(store_factory, 1)
    with pytest.raises(MergeError):
        m.merge(source=A, target=A)
    m.merge(source=B, target=A)
    with pytest.raises(MergeError):  # already resolves to A
        m.merge(source=B, target=A)


# ── coalesce honored on the served index ─────────────────────────────────────
def test_merged_owner_served_once_with_combined_rollups(service, store_factory) -> None:
    store = store_factory(1)
    m = OwnerMergeService(store.session, 1)
    m.merge(source=B, target=A)

    cands = service.list_candidates(store, merges=m)
    ids = [c["display_cluster_id"] for c in cands]
    assert ids.count(A) == 1 and B not in ids  # one merged row under the target
    assert C in ids  # untouched owner still listed
    merged = next(c for c in cands if c["display_cluster_id"] == A)
    # rollups combine A(AR,WV) + B(FL): states union, parcels/towers sum.
    assert set(merged["states"]) == {"AR", "FL", "WV"}
    assert merged["parcel_count"] == 4
    assert merged["tower_count"] == 6
    assert merged["distress_tier"] == "distressed"  # worst across members
    assert merged["in_oz"] is True  # any() across members
    assert merged["owner_name"] == "AMERICAN TOWERS LLC"  # survivor identity


def test_counts_reflect_dedup_after_merge(service, store_factory) -> None:
    store = store_factory(1)
    m = OwnerMergeService(store.session, 1)
    assert service.counts(store, merges=m) == {"candidates": 3, "my_leads": 0}
    m.merge(source=B, target=A)
    # 3 raw owners → 2 effective (A+B merged, C alone), all still New.
    assert service.counts(store, merges=m) == {"candidates": 2, "my_leads": 0}


def test_get_owner_resolves_merged_away_source(service, store_factory) -> None:
    store = store_factory(1)
    m = OwnerMergeService(store.session, 1)
    m.merge(source=B, target=A)
    # A request for the merged-away source id still finds the surviving owner
    # (the map links a tower by its raw cluster id).
    owner = service.get_owner(B, m)
    assert owner is not None
    assert owner["display_cluster_id"] == A


# ── lead-state reconciliation: target-wins + streams concatenate ─────────────
def test_lead_view_target_wins_and_streams_concatenate(service, store_factory) -> None:
    store = store_factory(1)
    # Work both clusters independently *before* merging.
    store.upsert(A, status="researching", notes="target note")
    store.append_attempt(B, channel="phone", outcome="left voicemail")

    m = OwnerMergeService(store.session, 1)
    m.merge(source=B, target=A)

    view = service.lead_view(store, A, merges=m)
    assert view["status"] == "researching"  # target's row wins
    assert view["notes"] == "target note"
    # the merged activity stream carries B's attempt + A's auto-logged status row
    channels = [a["channel"] for a in view["attempts"]]
    assert "phone" in channels and "status" in channels
    # and the merged-in cluster is listed so the UI can split it back out
    assert [mm["display_cluster_id"] for mm in view["merged_members"]] == [B]


def test_split_restores_each_clusters_own_lead_state(service, store_factory) -> None:
    store = store_factory(1)
    store.upsert(B, status="researching", notes="B was being worked")
    m = OwnerMergeService(store.session, 1)
    m.merge(source=B, target=A)
    # While merged, the view is served under A (target-wins → A's default New).
    assert service.lead_view(store, B, merges=m)["owner"]["display_cluster_id"] == A

    m.split(source=B)
    # B re-emerges as its own Lead with its original state intact.
    view_b = service.lead_view(store, B, merges=m)
    assert view_b["owner"]["display_cluster_id"] == B
    assert view_b["status"] == "researching"
    assert view_b["notes"] == "B was being worked"


# ── overrides survive an owners-index recompute, raw ids unchanged ───────────
def test_override_survives_index_recompute(tmp_path: Path, store_factory) -> None:
    path = tmp_path / "owners_index.json"
    path.write_text(json.dumps(SAMPLE))
    service = OwnersIndexService(path)
    store = store_factory(1)
    m = OwnerMergeService(store.session, 1)
    m.merge(source=B, target=A)

    # Recompute: rewrite the index (same raw cluster ids) and reload.
    path.write_text(json.dumps(SAMPLE))
    service.reload()
    # Raw ids in the file are untouched; the override (keyed on them) still holds.
    assert {o["display_cluster_id"] for o in json.loads(path.read_text())["owners"]} == {A, B, C}
    m_after = OwnerMergeService(store.session, 1)
    assert m_after.resolve(B) == A
    ids = [c["display_cluster_id"] for c in service.list_candidates(store, merges=m_after)]
    assert ids.count(A) == 1 and B not in ids


# ── tenant isolation ─────────────────────────────────────────────────────────
def test_overrides_are_tenant_scoped(service, store_factory) -> None:
    store1, store2 = store_factory(1), store_factory(2)
    OwnerMergeService(store1.session, 1).merge(source=B, target=A)

    m2 = OwnerMergeService(store2.session, 2)
    assert m2.resolve(B) == B  # tenant 2 never sees tenant 1's merge
    ids2 = [c["display_cluster_id"] for c in service.list_candidates(store2, merges=m2)]
    assert B in ids2 and A in ids2  # both still distinct for tenant 2
    assert service.counts(store2, merges=m2) == {"candidates": 3, "my_leads": 0}
