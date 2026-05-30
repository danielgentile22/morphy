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


# Additive columns introduced after Slice 1 that ``create_all`` cannot add to
# an *existing* ``lead`` table (it only creates missing tables). Slice 3 / #49
# adds the editable contact fields. ``''`` default + NOT NULL is valid
# ``ADD COLUMN`` DDL on both SQLite and Postgres.
_LEAD_ADDED_COLUMNS: dict[str, str] = {
    "contact_name": "VARCHAR(255)",
    "contact_phone": "VARCHAR(64)",
    "contact_email": "VARCHAR(320)",
    "best_channel": "VARCHAR(32)",
}


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
    """Back-fill columns added to an already-created ``lead`` table."""
    insp = inspect(eng)
    if "lead" not in insp.get_table_names():
        return  # nothing yet — create_all already built it with all columns
    existing = {c["name"] for c in insp.get_columns("lead")}
    missing = {n: t for n, t in _LEAD_ADDED_COLUMNS.items() if n not in existing}
    if not missing:
        return
    with eng.begin() as conn:
        for name, col_type in missing.items():
            conn.execute(text(f"ALTER TABLE lead ADD COLUMN {name} {col_type} NOT NULL DEFAULT ''"))


def get_db() -> Iterator[Session]:
    """FastAPI dependency: a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
