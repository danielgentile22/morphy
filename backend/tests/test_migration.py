"""The Alembic migration path (PRD #134).

``init_db`` brings any database to the current head: a fresh one by running
the migration chain from the baseline, a pre-Alembic one (built and
maintained by the retired additive path) by *stamping* the baseline its
schema already matches, then upgrading. These tests prove both routes on
the ``database_url`` fixture — SQLite by default, real Postgres via
``MORPHY_TEST_DATABASE_URL`` / ``MORPHY_TEST_TESTCONTAINERS=1`` (TESTING.md
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

from backend.app import credentials_store
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
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert head is not None
    return head


def _stamped_revision(eng: Engine) -> str:
    with eng.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _alembic_cfg(eng: Engine):
    """An Alembic config bound to ``eng`` (mirrors ``db.init_db``), for driving
    targeted up/down migrations in tests."""
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("prepend_sys_path", "")
    cfg.attributes["connection"] = eng
    return cfg


def _has_table(eng: Engine, table: str) -> bool:
    return table in inspect(eng).get_table_names()


# Schema added by migrations *after* the 0001 baseline. A real pre-Alembic
# database is frozen at the baseline schema (the retired additive path produced
# exactly the baseline), so the adoption tests below, which use a create_all'd
# *current-head* DB to stand in for that legacy DB, strip these first to restore
# the baseline shape before exercising stamp-baseline + upgrade-to-head. Add an
# entry here when a new migration adds a column (or a DROP TABLE line for a
# new table).
_POST_BASELINE_COLUMNS = (("credential", "read_only"),)


def _strip_post_baseline(eng: Engine) -> None:
    with eng.begin() as conn:
        for table, column in _POST_BASELINE_COLUMNS:
            conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))


def _columns(eng: Engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(eng).get_columns(table)}


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
    _strip_post_baseline(eng)  # a pre-Alembic DB is baseline-shaped
    LeadStore(Session(bind=eng, future=True), tenant_id=1).upsert("old1", status="researching")
    TaskStore(Session(bind=eng, future=True), tenant_id=1).create(title="legacy task")
    assert "alembic_version" not in inspect(eng).get_table_names()

    init_db(eng)

    assert _stamped_revision(eng) == _head_revision()
    store = LeadStore(Session(bind=eng, future=True), tenant_id=1)
    old = store.get_lead("old1")
    assert old is not None
    assert (old.status, old.contact_name) == ("researching", "")
    store.upsert("old1", contact={"contact_name": "Jane Roe"})
    reloaded = LeadStore(Session(bind=eng, future=True), 1).get_lead("old1")
    assert reloaded is not None
    assert reloaded.contact_name == "Jane Roe"

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
    _strip_post_baseline(eng)  # a pre-Alembic DB is baseline-shaped

    init_db(eng)

    assert _stamped_revision(eng) == _head_revision()
    store = LeadStore(Session(bind=eng, future=True), tenant_id=1)
    old = store.get_lead("old1")
    assert old is not None
    assert old.contact_name == ""
    store.upsert("old1", contact={"contact_name": "Jane Roe"})
    reloaded = LeadStore(Session(bind=eng, future=True), 1).get_lead("old1")
    assert reloaded is not None
    assert reloaded.contact_name == "Jane Roe"
    # The pre-#106 attempt reads as outbound (the ALTER's DEFAULT back-fill).
    attempts = LeadStore(Session(bind=eng, future=True), 1).list_attempts("old1")
    assert [a.direction for a in attempts] == ["outbound"]


def test_init_db_is_idempotent(migration_engine: Engine) -> None:
    init_db(migration_engine)
    init_db(migration_engine)  # no-op second run must not error
    assert _stamped_revision(migration_engine) == _head_revision()


# ── 0003: read-only credentials + the Ask Claude log retired (ADR-077) ────────
def test_read_only_revision_up_down_keeps_existing_credentials_writable(
    migration_engine: Engine,
) -> None:
    """0003 adds ``credential.read_only`` with a false default, so a credential
    that existed before the upgrade keeps full write access, and drops the
    retired ``ask_log`` table. ``downgrade`` restores the 0002 shape."""
    from alembic import command

    eng = migration_engine
    cfg = _alembic_cfg(eng)
    command.upgrade(cfg, "0002")
    assert _has_table(eng, "ask_log")
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO credential (username, password_hash, team, created_at, updated_at)"
                " VALUES ('alice', 'pbkdf2$x', 'acme', '2026-01-01', '2026-01-01')"
            )
        )

    command.upgrade(cfg, "head")
    assert not _has_table(eng, "ask_log")
    assert "read_only" in _columns(eng, "credential")
    entry = credentials_store.get(Session(bind=eng, future=True), "alice")
    assert entry is not None
    assert entry.read_only is False

    command.downgrade(cfg, "0002")
    assert _has_table(eng, "ask_log")
    assert "read_only" not in _columns(eng, "credential")
    assert _stamped_revision(eng) == "0002"

    command.upgrade(cfg, "head")
    assert _stamped_revision(eng) == _head_revision()
