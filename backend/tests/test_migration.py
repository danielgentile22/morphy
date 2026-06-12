"""The Alembic migration path (PRD #134).

``init_db`` brings any database to the current head: a fresh one by running
the migration chain from the baseline, a pre-Alembic one (built and
maintained by the retired additive path) by *stamping* the baseline its
schema already matches, then upgrading. These tests prove both routes on
the ``database_url`` fixture — SQLite by default, real Postgres via
``PILOT_TEST_DATABASE_URL`` / ``PILOT_TEST_TESTCONTAINERS=1`` (TESTING.md
§11.1) — and keep the retired ``test_migration`` scenarios: legacy rows
survive adoption, contact writes work end-to-end, the first registered
team still inherits tenant 1.

The behavior suite's fixtures stay on fast ``create_all`` (conftest);
parity between the two schema paths is asserted here, once.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db import _ALEMBIC_INI, Base, init_db
from backend.app.lead_store import LeadStore
from backend.app.task_store import TaskStore
from backend.app.tenant_service import TenantService


@pytest.fixture
def migration_engine(database_url: str) -> Iterator[Engine]:
    """A *bare* engine — no ``create_all`` (unlike conftest's ``engine``), so
    each test controls the starting schema. Teardown removes every table
    including ``alembic_version`` (the Postgres database is shared)."""
    kwargs: dict = {"future": True}
    if database_url.startswith("sqlite") and ":memory:" in database_url:
        kwargs.update(connect_args={"check_same_thread": False}, poolclass=StaticPool)
    eng = create_engine(database_url, **kwargs)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)
        with eng.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        eng.dispose()


def _schema_snapshot(eng: Engine) -> dict:
    """Reflected schema, normalized for comparison: tables → columns
    (type, nullability), primary key, indexes, unique constraints."""
    insp = inspect(eng)
    snap: dict = {}
    for table in insp.get_table_names():
        if table == "alembic_version":
            continue
        snap[table] = {
            "columns": {
                c["name"]: (str(c["type"]), bool(c["nullable"])) for c in insp.get_columns(table)
            },
            "pk": tuple(insp.get_pk_constraint(table)["constrained_columns"]),
            "indexes": {
                i["name"]: (tuple(i["column_names"]), bool(i["unique"]))
                for i in insp.get_indexes(table)
            },
            "uniques": {
                u["name"]: tuple(u["column_names"]) for u in insp.get_unique_constraints(table)
            },
        }
    return snap


def _head_revision() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("prepend_sys_path", "")
    return ScriptDirectory.from_config(cfg).get_current_head()


def _stamped_revision(eng: Engine) -> str:
    with eng.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


# ── parity: the migration chain must build exactly the create_all schema ─────
def test_upgrade_to_head_matches_create_all(migration_engine: Engine) -> None:
    """The behavior tests run on ``create_all``; production runs on the
    migration chain. This is the one assertion that they are the same
    schema — columns, nullability, PKs, indexes, uniques."""
    Base.metadata.create_all(migration_engine)
    via_create_all = _schema_snapshot(migration_engine)
    Base.metadata.drop_all(migration_engine)

    init_db(migration_engine)  # fresh DB → runs baseline → head
    via_migrations = _schema_snapshot(migration_engine)

    assert via_migrations == via_create_all
    assert _stamped_revision(migration_engine) == _head_revision()


# ── adoption: a pre-Alembic database stamps + upgrades in place ──────────────
def test_pre_alembic_db_is_stamped_and_upgraded_with_rows_intact(
    migration_engine: Engine,
) -> None:
    """A database the retired additive path maintained (= current schema, no
    ``alembic_version``) is adopted without touching its data: rows survive,
    contact writes work end-to-end, and the first registered team still
    receives tenant 1 — inheriting the pre-teams board (#86)."""
    eng = migration_engine
    Base.metadata.create_all(eng)
    LeadStore(Session(bind=eng, future=True), tenant_id=1).upsert("old1", status="researching")
    TaskStore(Session(bind=eng, future=True), tenant_id=1).create(title="legacy task")
    assert "alembic_version" not in inspect(eng).get_table_names()

    init_db(eng)

    assert _stamped_revision(eng) == _head_revision()
    store = LeadStore(Session(bind=eng, future=True), tenant_id=1)
    old = store.get_lead("old1")
    assert (old.status, old.contact_name) == ("researching", "")
    store.upsert("old1", contact={"contact_name": "Jane Roe"})
    assert LeadStore(Session(bind=eng, future=True), 1).get_lead("old1").contact_name == "Jane Roe"

    t = TaskStore(Session(bind=eng, future=True), 1).list()[0]
    assert (t.title, t.priority, t.source, t.labels) == ("legacy task", "none", "manual", "")

    assert TenantService(Session(bind=eng, future=True)).find_or_create("original-team").id == 1


def test_prod_shaped_tables_adopt_cleanly(migration_engine: Engine) -> None:
    """Production's ``lead`` and ``contact_attempt`` tables were built by
    early slices and grew later columns via ``ALTER TABLE ... ADD COLUMN ...
    DEFAULT`` (#49, #106, #112), so their DDL carries literal defaults the
    models never declared. Frozen here verbatim: that exact shape must stamp
    + upgrade cleanly and serve the stores — old attempts stay outbound, old
    leads accept contact writes."""
    eng = migration_engine
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE lead (
                    tenant_id INTEGER NOT NULL,
                    display_cluster_id VARCHAR(64) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    PRIMARY KEY (tenant_id, display_cluster_id)
                )
                """
            )
        )
        for ddl in (
            "contact_name VARCHAR(255) NOT NULL DEFAULT ''",
            "contact_phone VARCHAR(64) NOT NULL DEFAULT ''",
            "contact_email VARCHAR(320) NOT NULL DEFAULT ''",
            "best_channel VARCHAR(32) NOT NULL DEFAULT ''",
        ):
            conn.execute(text(f"ALTER TABLE lead ADD COLUMN {ddl}"))
        conn.execute(
            text(
                "INSERT INTO lead (tenant_id, display_cluster_id, status, notes)"
                " VALUES (1, 'old1', 'researching', '')"
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE contact_attempt (
                    id INTEGER PRIMARY KEY,
                    tenant_id INTEGER NOT NULL,
                    display_cluster_id VARCHAR(64) NOT NULL,
                    occurred_on DATE NOT NULL,
                    channel VARCHAR(32) NOT NULL,
                    outcome VARCHAR(64) NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP
                )
                """
            )
        )
        for ddl in (
            "direction VARCHAR(16) NOT NULL DEFAULT 'outbound'",
            "logged_by_user_id INTEGER",
        ):
            conn.execute(text(f"ALTER TABLE contact_attempt ADD COLUMN {ddl}"))
        conn.execute(
            text(
                "INSERT INTO contact_attempt"
                " (tenant_id, display_cluster_id, occurred_on, channel)"
                " VALUES (1, 'old1', '2026-01-01', 'phone')"
            )
        )
    Base.metadata.create_all(eng)  # the remaining tables; existing ones stay as-is

    init_db(eng)

    assert _stamped_revision(eng) == _head_revision()
    store = LeadStore(Session(bind=eng, future=True), tenant_id=1)
    assert store.get_lead("old1").contact_name == ""
    store.upsert("old1", contact={"contact_name": "Jane Roe"})
    assert LeadStore(Session(bind=eng, future=True), 1).get_lead("old1").contact_name == "Jane Roe"
    # The pre-#106 attempt reads as outbound (the ALTER's DEFAULT back-fill).
    attempts = LeadStore(Session(bind=eng, future=True), 1).list_attempts("old1")
    assert [a.direction for a in attempts] == ["outbound"]


def test_init_db_is_idempotent(migration_engine: Engine) -> None:
    init_db(migration_engine)
    init_db(migration_engine)  # no-op second run must not error
    assert _stamped_revision(migration_engine) == _head_revision()
