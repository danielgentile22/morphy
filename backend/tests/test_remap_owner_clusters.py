"""Owner-cluster key remap (ADR-075 / #221) — the migration that repoints lead
state + merge overrides when the cross-state key recipe changes.

Two layers: the pure ``plan_*`` policy functions (split duplicates, collision
merges, same-state override pairing) with no DB, and the ``remap`` DB apply on a
real session incl. idempotency + dry-run.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.app.models import ContactAttempt, Lead, OwnerClusterOverride
from backend.app.remap_owner_clusters import (
    build_expander,
    plan_attempt_targets,
    plan_leads,
    plan_overrides,
    remap,
)


# ── pure planners ────────────────────────────────────────────────────────────
def test_expander_maps_unmapped_id_to_itself():
    expand = build_expander({"A": [{"new": "A_05", "state": "05"}]})
    assert expand("A") == [("A_05", "05")]
    assert expand("unknown") == [("unknown", "")]  # inert-safe


def test_plan_attempt_targets_one_split_and_unmapped():
    expand = build_expander(
        {
            "one": [{"new": "one_05", "state": "05"}],
            "split": [{"new": "s_05", "state": "05"}, {"new": "s_54", "state": "54"}],
        }
    )
    assert plan_attempt_targets("one", expand) == ["one_05"]
    assert plan_attempt_targets("split", expand) == ["s_05", "s_54"]
    assert plan_attempt_targets("nope", expand) == []  # unmapped → leave alone


def test_plan_leads_one_to_one_repoints():
    expand = build_expander({"A": [{"new": "A_05", "state": "05"}]})
    rows, merged = plan_leads(
        [{"tenant_id": 1, "display_cluster_id": "A", "status": "contacted", "notes": "hi"}], expand
    )
    assert merged == 0
    assert rows == [
        {"tenant_id": 1, "display_cluster_id": "A_05", "status": "contacted", "notes": "hi"}
    ]


def test_plan_leads_split_duplicates_to_each_new_subcluster():
    expand = build_expander({"X": [{"new": "X_05", "state": "05"}, {"new": "X_54", "state": "54"}]})
    rows, merged = plan_leads(
        [{"tenant_id": 1, "display_cluster_id": "X", "status": "researching", "notes": "n"}], expand
    )
    assert merged == 0
    assert {r["display_cluster_id"] for r in rows} == {"X_05", "X_54"}
    assert all(r["status"] == "researching" and r["notes"] == "n" for r in rows)


def test_plan_leads_merge_keeps_most_advanced_and_concats_notes():
    # Two aliased-towerco fragments collide on one new id → merge.
    expand = build_expander(
        {
            "A": [{"new": "M", "state": ""}],
            "B": [{"new": "M", "state": ""}],
        }
    )
    rows, merged = plan_leads(
        [
            {"tenant_id": 1, "display_cluster_id": "A", "status": "contacted", "notes": "spoke"},
            {"tenant_id": 1, "display_cluster_id": "B", "status": "new", "notes": "todo"},
        ],
        expand,
    )
    assert merged == 1 and len(rows) == 1
    row = rows[0]
    assert row["display_cluster_id"] == "M"
    assert row["status"] == "contacted"  # most-advanced wins
    assert "spoke" in row["notes"] and "todo" in row["notes"]  # both preserved


def test_plan_overrides_pairs_by_state_and_drops_self_edges():
    expand = build_expander(
        {
            "S": [{"new": "S05", "state": "05"}, {"new": "S54", "state": "54"}],
            "T": [{"new": "T05", "state": "05"}, {"new": "T54", "state": "54"}],
        }
    )
    out = plan_overrides(
        [{"tenant_id": 1, "source_cluster_id": "S", "target_cluster_id": "T"}], expand
    )
    assert {(o["source_cluster_id"], o["target_cluster_id"]) for o in out} == {
        ("S05", "T05"),
        ("S54", "T54"),  # same-state pairing
    }


# ── DB apply ─────────────────────────────────────────────────────────────────
_MAP = {"OLD": [{"new": "NEW05", "state": "05"}]}


def _seed(session: Session) -> None:
    session.add(Lead(tenant_id=1, display_cluster_id="OLD", status="contacted", notes="hi"))
    session.add(ContactAttempt(tenant_id=1, display_cluster_id="OLD", channel="call"))
    session.commit()


def test_remap_repoints_lead_and_attempts(new_session: Callable[[], Session]):
    s = new_session()
    _seed(s)
    stats = remap(s, _MAP)
    assert stats["leads_remapped"] == 1 and stats["attempts_repointed"] == 1

    check = new_session()
    assert check.get(Lead, (1, "OLD")) is None
    moved = check.get(Lead, (1, "NEW05"))
    assert moved is not None and moved.status == "contacted" and moved.notes == "hi"
    attempts = check.query(ContactAttempt).all()
    assert [a.display_cluster_id for a in attempts] == ["NEW05"]


def test_remap_is_idempotent(new_session: Callable[[], Session]):
    s = new_session()
    _seed(s)
    remap(s, _MAP)
    # A second run finds no OLD keys left → a clean no-op.
    stats2 = remap(new_session(), _MAP)
    assert stats2 == {
        "attempts_repointed": 0,
        "attempts_duplicated": 0,
        "leads_remapped": 0,
        "leads_merged": 0,
        "overrides_remapped": 0,
    }


def test_remap_dry_run_changes_nothing(new_session: Callable[[], Session]):
    s = new_session()
    _seed(s)
    stats = remap(s, _MAP, dry_run=True)
    assert stats["leads_remapped"] == 1  # counted...
    check = new_session()
    assert check.get(Lead, (1, "OLD")) is not None  # ...but nothing written


def test_remap_migrates_override_edges(new_session: Callable[[], Session]):
    s = new_session()
    s.add(OwnerClusterOverride(tenant_id=1, source_cluster_id="S", target_cluster_id="T"))
    s.commit()
    mapping = {
        "S": [{"new": "S05", "state": "05"}],
        "T": [{"new": "T05", "state": "05"}],
    }
    remap(s, mapping)
    check = new_session()
    rows = check.query(OwnerClusterOverride).all()
    assert [(r.source_cluster_id, r.target_cluster_id) for r in rows] == [("S05", "T05")]


# ── ADR-075 regression: multi-state alias keys (#221 follow-up) ───────────────
# A curated towerco's cross-state key is state-independent, so the SAME new key
# recurs once per state it owns land in. The map lists it once per state; the
# remap must repoint that once (never treat the repeats as a split and DUPLICATE
# the row), and a self-map (old==new) is a no-op. Before this, American Tower /
# SBA leads re-cloned their attempts on every deploy run.


def test_plan_attempt_targets_collapses_repeated_alias_target():
    expand = build_expander({"sba": [{"new": "AT", "state": "05"}, {"new": "AT", "state": "54"}]})
    assert plan_attempt_targets("sba", expand) == ["AT"]  # one repoint, not ["AT","AT"]


def test_plan_attempt_targets_self_map_is_noop():
    expand = build_expander({"K": [{"new": "K", "state": "05"}, {"new": "K", "state": "54"}]})
    assert plan_attempt_targets("K", expand) == []


def test_plan_leads_self_map_does_not_self_merge():
    expand = build_expander({"K": [{"new": "K", "state": "05"}, {"new": "K", "state": "54"}]})
    rows, merged = plan_leads(
        [{"tenant_id": 1, "display_cluster_id": "K", "status": "researching", "notes": ""}], expand
    )
    assert merged == 0
    assert [r["display_cluster_id"] for r in rows] == ["K"]


def test_remap_multistate_alias_never_duplicates(new_session: Callable[[], Session]):
    s = new_session()
    s.add(Lead(tenant_id=1, display_cluster_id="AT", status="researching", notes=""))
    s.add(
        ContactAttempt(
            tenant_id=1, display_cluster_id="AT", channel="status", outcome="new→researching"
        )
    )
    s.commit()
    # AT owns land in two states → its alias key repeats; a naive remap would
    # clone the attempt once per state, every run.
    mapping = {"AT": [{"new": "AT", "state": "05"}, {"new": "AT", "state": "54"}]}
    stats = remap(s, mapping)
    assert stats["attempts_duplicated"] == 0 and stats["leads_merged"] == 0
    remap(new_session(), mapping)  # second pass — still no growth
    check = new_session()
    assert check.query(ContactAttempt).count() == 1  # not 2, 3, ...
    assert check.query(Lead).count() == 1
