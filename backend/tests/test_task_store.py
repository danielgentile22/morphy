"""TaskStore behavior (UI overhaul P2 / #107): CRUD, status lifecycle,
completed_at stamping, and tenant isolation."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.task_store import InvalidTaskStatus, TaskStore


def _store(engine: Engine, tenant_id: int) -> TaskStore:
    return TaskStore(Session(bind=engine, future=True), tenant_id)


def test_create_defaults_to_open_with_no_completed_at(engine: Engine) -> None:
    t = _store(engine, 1).create(title="Call Michael", description="re: tower")
    assert t.id is not None
    assert (t.title, t.description, t.status) == ("Call Michael", "re: tower", "open")
    assert t.completed_at is None


def test_create_and_list_newest_first(engine: Engine) -> None:
    store = _store(engine, 1)
    store.create(title="first")
    store.create(title="second")
    titles = [t.title for t in _store(engine, 1).list()]
    assert titles == ["second", "first"]  # newest first


def test_get_returns_the_task_for_its_tenant(engine: Engine) -> None:
    t = _store(engine, 1).create(title="x")
    assert _store(engine, 1).get(t.id) is not None
    assert _store(engine, 1).get(t.id).title == "x"


def test_completing_a_task_stamps_completed_at(engine: Engine) -> None:
    t = _store(engine, 1).create(title="ship it")
    updated = _store(engine, 1).update(t.id, status="done")
    assert updated is not None
    assert updated.status == "done"
    assert updated.completed_at is not None


def test_reopening_a_done_task_clears_completed_at(engine: Engine) -> None:
    store = _store(engine, 1)
    t = store.create(title="x", status="done")
    assert t.completed_at is not None
    reopened = _store(engine, 1).update(t.id, status="open")
    assert reopened.status == "open"
    assert reopened.completed_at is None


def test_update_title_and_description(engine: Engine) -> None:
    t = _store(engine, 1).create(title="old", description="d1")
    updated = _store(engine, 1).update(t.id, title="new", description="d2")
    assert (updated.title, updated.description) == ("new", "d2")


def test_partial_update_leaves_other_fields_untouched(engine: Engine) -> None:
    t = _store(engine, 1).create(title="keep", description="keep-desc")
    updated = _store(engine, 1).update(t.id, status="in_progress")
    assert (updated.title, updated.description, updated.status) == (
        "keep",
        "keep-desc",
        "in_progress",
    )


def test_invalid_status_is_rejected(engine: Engine) -> None:
    store = _store(engine, 1)
    with pytest.raises(InvalidTaskStatus):
        store.create(title="x", status="bogus")
    t = store.create(title="y")
    with pytest.raises(InvalidTaskStatus):
        store.update(t.id, status="nope")


def test_delete_removes_the_task(engine: Engine) -> None:
    t = _store(engine, 1).create(title="trash")
    assert _store(engine, 1).delete(t.id) is True
    assert _store(engine, 1).get(t.id) is None
    assert _store(engine, 1).delete(t.id) is False  # already gone


# ── tenant isolation ──────────────────────────────────────────────────────────
def test_tasks_are_tenant_scoped(engine: Engine) -> None:
    t = _store(engine, 1).create(title="tenant-1 only")
    # Tenant 2 cannot see, fetch, update, or delete tenant 1's task.
    assert _store(engine, 2).list() == []
    assert _store(engine, 2).get(t.id) is None
    assert _store(engine, 2).update(t.id, status="done") is None
    assert _store(engine, 2).delete(t.id) is False
    # …and tenant 1's task is untouched.
    assert _store(engine, 1).get(t.id).status == "open"


def test_created_by_is_recorded(engine: Engine) -> None:
    t = _store(engine, 1).create(title="mine", created_by_user_id=42)
    assert _store(engine, 1).get(t.id).created_by_user_id == 42


# ── links / assignee / labels / priority (#110) ──────────────────────────────
from datetime import date  # noqa: E402

from backend.app.task_store import InvalidTaskPriority, normalize_labels  # noqa: E402


def test_create_with_links_and_assignee(engine: Engine) -> None:
    t = _store(engine, 1).create(
        title="follow up",
        lead_cluster_id="cid1",
        tower_asr="000046",
        assignee_user_id=7,
        priority="high",
        due_date=date(2026, 9, 1),
    )
    got = _store(engine, 1).get(t.id)
    assert got.lead_cluster_id == "cid1"
    assert got.tower_asr == "000046"
    assert got.assignee_user_id == 7
    assert got.priority == "high"
    assert got.due_date == date(2026, 9, 1)
    assert got.source == "manual"


def test_labels_are_normalized() -> None:
    assert normalize_labels(" Dev , outreach,dev ,, ") == "dev,outreach"
    assert normalize_labels(["A", "b", "A"]) == "a,b"
    assert normalize_labels(None) == ""


def test_invalid_priority_rejected(engine: Engine) -> None:
    with pytest.raises(InvalidTaskPriority):
        _store(engine, 1).create(title="x", priority="urgent")


def test_update_clears_a_link_with_explicit_none(engine: Engine) -> None:
    t = _store(engine, 1).create(title="x", lead_cluster_id="cid1")
    # Sentinel: passing None clears; omitting leaves unchanged.
    _store(engine, 1).update(t.id, lead_cluster_id=None)
    assert _store(engine, 1).get(t.id).lead_cluster_id is None


def test_update_omitting_a_link_leaves_it(engine: Engine) -> None:
    t = _store(engine, 1).create(title="x", lead_cluster_id="cid1")
    _store(engine, 1).update(t.id, title="renamed")  # link not mentioned
    assert _store(engine, 1).get(t.id).lead_cluster_id == "cid1"


# ── list_filtered (#110) ──────────────────────────────────────────────────────
def _seed_filter_set(engine: Engine) -> None:
    s = _store(engine, 1)
    s.create(
        title="call Michael",
        description="re: tower",
        assignee_user_id=1,
        priority="high",
        lead_cluster_id="cidA",
        labels=["outreach"],
    )
    s.create(
        title="ship feature",
        description="web app",
        assignee_user_id=2,
        status="in_progress",
        labels=["dev"],
        tower_asr="000046",
    )
    s.create(title="buy coffee", priority="low")  # unassigned, no links


def test_filter_by_assignee_and_unassigned(engine: Engine) -> None:
    _seed_filter_set(engine)
    assert len(_store(engine, 1).list_filtered(assignee_user_id=1)) == 1
    assert len(_store(engine, 1).list_filtered(unassigned=True)) == 1


def test_filter_by_status_priority_link_label(engine: Engine) -> None:
    _seed_filter_set(engine)
    s = _store(engine, 1)
    assert len(s.list_filtered(status="in_progress")) == 1
    assert len(s.list_filtered(priority="high")) == 1
    assert len(s.list_filtered(lead_cluster_id="cidA")) == 1
    assert len(s.list_filtered(tower_asr="000046")) == 1
    assert len(s.list_filtered(label="dev")) == 1


def test_free_text_search_matches_title_and_description(engine: Engine) -> None:
    _seed_filter_set(engine)
    s = _store(engine, 1)
    assert {t.title for t in s.list_filtered(q="michael")} == {"call Michael"}
    assert {t.title for t in s.list_filtered(q="web app")} == {"ship feature"}  # description
    assert len(s.list_filtered(q="zzz")) == 0


def test_filter_is_tenant_scoped(engine: Engine) -> None:
    _seed_filter_set(engine)
    assert _store(engine, 2).list_filtered() == []
