"""SQLAlchemy engine + session plumbing.

DB-agnostic: SQLite for local dev (default), Postgres in deploy/CI via
``DATABASE_URL``. The ORM models use no dialect-specific types, so the
tenant-isolation behavior is identical on either backend (isolation is
application-level — every query filters by ``tenant_id``).
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


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
    """Create tables if absent. Slice 1 has no migrations (Alembic is later)."""
    # Import models so they register on Base.metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(eng or engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
