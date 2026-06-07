"""The additive ``lead`` contact-column migration (Slice 3 / #49).

An existing DB from an earlier slice has a ``lead`` table without the
contact columns; ``init_db`` must back-fill them so the upgraded code can
read/write contact fields without a manual schema edit.
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db import _LEAD_ADDED_COLUMNS, init_db
from backend.app.lead_store import LeadStore

# The pre-Slice-3 ``lead`` table — no contact columns.
_LEGACY_LEAD_DDL = """
CREATE TABLE lead (
    tenant_id INTEGER NOT NULL,
    display_cluster_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'new',
    notes TEXT NOT NULL DEFAULT '',
    created_at DATETIME,
    updated_at DATETIME,
    PRIMARY KEY (tenant_id, display_cluster_id)
)
"""


def _legacy_engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    with eng.begin() as conn:
        conn.execute(text(_LEGACY_LEAD_DDL))
        conn.execute(
            text(
                "INSERT INTO lead (tenant_id, display_cluster_id, status) VALUES (1, 'old1', 'researching')"
            )
        )
    return eng


def test_init_db_backfills_contact_columns_on_existing_table() -> None:
    eng = _legacy_engine()
    before = {c["name"] for c in inspect(eng).get_columns("lead")}
    assert not (set(_LEAD_ADDED_COLUMNS) & before)  # none present yet

    init_db(eng)  # create_all is a no-op for the existing table; migration runs

    after = {c["name"] for c in inspect(eng).get_columns("lead")}
    assert set(_LEAD_ADDED_COLUMNS).issubset(after)


def test_migration_preserves_existing_rows_and_allows_contact_writes() -> None:
    eng = _legacy_engine()
    init_db(eng)

    store = LeadStore(Session(bind=eng, future=True), tenant_id=1)
    # the legacy row survived and its new columns default to ''
    old = store.get_lead("old1")
    assert old is not None
    assert (old.status, old.contact_name) == ("researching", "")
    # and contact writes now work end-to-end
    store.upsert("old1", contact={"contact_name": "Jane Roe"})
    assert LeadStore(Session(bind=eng, future=True), 1).get_lead("old1").contact_name == "Jane Roe"


def test_init_db_is_idempotent() -> None:
    eng = _legacy_engine()
    init_db(eng)
    init_db(eng)  # second run must not error (all columns already present)
    after = {c["name"] for c in inspect(eng).get_columns("lead")}
    assert set(_LEAD_ADDED_COLUMNS).issubset(after)


# ── the tenant table (#86) is additive ────────────────────────────────────────
def test_init_db_adds_the_tenant_table_to_an_existing_db() -> None:
    """A dev DB from before teams existed (lead rows under tenant 1, no
    ``tenant`` table) boots with no manual steps, and the first registered
    team picks up tenant id 1 — inheriting that pre-existing board."""
    eng = _legacy_engine()  # has a populated lead table, no tenant table
    assert "tenant" not in inspect(eng).get_table_names()

    init_db(eng)

    assert "tenant" in inspect(eng).get_table_names()
    # The legacy lead rows survived…
    store = LeadStore(Session(bind=eng, future=True), tenant_id=1)
    assert store.get_lead("old1") is not None
    # …and the first team registered on this DB receives tenant id 1.
    from backend.app.tenant_service import TenantService

    tenant = TenantService(Session(bind=eng, future=True)).find_or_create("original-team")
    assert tenant.id == 1


# ── #110 fleshed out task + app_user with additive columns ────────────────────
_LEGACY_TASK_DDL = """
CREATE TABLE task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    created_by_user_id INTEGER,
    created_at DATETIME,
    updated_at DATETIME,
    completed_at DATETIME
)
"""


def test_init_db_backfills_task_and_user_columns() -> None:
    """A #107-era ``task`` table (no links/assignee/priority) + a pre-#110
    ``app_user`` (no display_name) get the new columns added, old rows
    back-filling to safe defaults."""
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    with eng.begin() as conn:
        conn.execute(text(_LEGACY_TASK_DDL))
        conn.execute(text("INSERT INTO task (tenant_id, title) VALUES (1, 'legacy task')"))

    init_db(eng)

    cols = {c["name"] for c in inspect(eng).get_columns("task")}
    assert {
        "priority",
        "due_date",
        "assignee_user_id",
        "lead_cluster_id",
        "tower_asr",
        "labels",
        "source",
    } <= cols
    assert "display_name" in {c["name"] for c in inspect(eng).get_columns("app_user")}
    # the legacy task survived and back-filled to the defaults
    from backend.app.task_store import TaskStore

    t = TaskStore(Session(bind=eng, future=True), 1).list()[0]
    assert (t.title, t.priority, t.source, t.labels) == ("legacy task", "none", "manual", "")
    assert t.due_date is None and t.lead_cluster_id is None
