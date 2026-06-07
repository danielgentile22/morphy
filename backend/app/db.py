"""SQLAlchemy engine + session plumbing.

DB-agnostic: SQLite for local dev (default), Postgres in deploy/CI via
``DATABASE_URL``. The ORM models use no dialect-specific types, so the
tenant-isolation behavior is identical on either backend (isolation is
application-level — every query filters by ``tenant_id``).
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


# Additive columns introduced after a table first shipped that ``create_all``
# cannot add to an *existing* table (it only creates missing tables). Each
# value is the full ``ADD COLUMN`` type + constraint DDL (valid on both SQLite
# and Postgres) — a NOT NULL column carries a DEFAULT to back-fill old rows; a
# nullable column omits both.
#
# Slice 3 / #49 added the editable contact fields to ``lead``.
_LEAD_ADDED_COLUMNS: dict[str, str] = {
    "contact_name": "VARCHAR(255) NOT NULL DEFAULT ''",
    "contact_phone": "VARCHAR(64) NOT NULL DEFAULT ''",
    "contact_email": "VARCHAR(320) NOT NULL DEFAULT ''",
    "best_channel": "VARCHAR(32) NOT NULL DEFAULT ''",
}
# UI overhaul P2 / #106 added ``direction`` to the activity log; existing rows
# are outbound touches (the only kind before replies existed).
_ATTEMPT_ADDED_COLUMNS: dict[str, str] = {
    "direction": "VARCHAR(16) NOT NULL DEFAULT 'outbound'",
    # Who logged the activity — the teammate dimension (#112/#113).
    "logged_by_user_id": "INTEGER",
}
# UI overhaul P2 / #110 fleshed out ``task`` (links / assignee / due / priority
# / labels / source) and added a display name to ``app_user``.
_TASK_ADDED_COLUMNS: dict[str, str] = {
    "priority": "VARCHAR(8) NOT NULL DEFAULT 'none'",
    "due_date": "DATE",
    "assignee_user_id": "INTEGER",
    "lead_cluster_id": "VARCHAR(64)",
    "tower_asr": "VARCHAR(32)",
    "labels": "VARCHAR(512) NOT NULL DEFAULT ''",
    "source": "VARCHAR(8) NOT NULL DEFAULT 'manual'",
}
_USER_ADDED_COLUMNS: dict[str, str] = {
    "display_name": "VARCHAR(255) NOT NULL DEFAULT ''",
}
_ADDITIVE_MIGRATIONS: tuple[tuple[str, dict[str, str]], ...] = (
    ("lead", _LEAD_ADDED_COLUMNS),
    ("contact_attempt", _ATTEMPT_ADDED_COLUMNS),
    ("task", _TASK_ADDED_COLUMNS),
    ("app_user", _USER_ADDED_COLUMNS),
)


def make_engine(url: str | None = None) -> Engine:
    """Build an engine; SQLite gets the cross-thread connect args FastAPI needs."""
    db_url = url or settings.database_url
    kwargs: dict = {"future": True}
    if db_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(db_url, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db(eng: Engine | None = None) -> None:
    """Create tables if absent, then apply lightweight additive migrations.

    Fresh DBs get every column from ``create_all``; an existing DB from an
    earlier slice gets new columns back-filled by ``_migrate_added_columns``
    (a stand-in for Alembic, which lands later)."""
    # Import models so they register on Base.metadata before create_all.
    from . import models  # noqa: F401

    target = eng or engine
    Base.metadata.create_all(target)
    _migrate_added_columns(target)


def _migrate_added_columns(eng: Engine) -> None:
    """Back-fill columns added to already-created tables (additive only)."""
    insp = inspect(eng)
    table_names = set(insp.get_table_names())
    for table, columns in _ADDITIVE_MIGRATIONS:
        if table not in table_names:
            continue  # create_all already built it with all columns
        existing = {c["name"] for c in insp.get_columns(table)}
        missing = {n: ddl for n, ddl in columns.items() if n not in existing}
        if not missing:
            continue
        with eng.begin() as conn:
            for name, ddl in missing.items():
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def get_db() -> Iterator[Session]:
    """FastAPI dependency: a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
