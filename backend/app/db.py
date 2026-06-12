"""SQLAlchemy engine + session plumbing.

DB-agnostic: SQLite for local dev (default), Postgres in deploy/CI via
``DATABASE_URL``. The ORM models use no dialect-specific types, so the
tenant-isolation behavior is identical on either backend (isolation is
application-level — every query filters by ``tenant_id``).

Schema changes ship as Alembic revisions (PRD #134): edit models.py, then
``uv run alembic -c backend/alembic.ini revision --autogenerate`` and review
the output. ``init_db`` brings any database to head at app boot.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


# The revision whose schema matches what the retired additive ``init_db``
# path produced. A database with tables but no ``alembic_version`` was
# maintained by that path — it is adopted by *stamping* this revision
# (recording "you are already here"), never by replaying the baseline.
_BASELINE_REVISION = "0001"
_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


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
    """Bring the schema to the current Alembic head (PRD #134).

    A fresh database gets everything by running the migration chain; a
    pre-Alembic database (tables present, no ``alembic_version``) is stamped
    at the baseline its schema already matches, then upgraded. Runs at app
    boot — safe while the deploy is one machine with one writer (ADR-064);
    if that ever changes, this moves to a release step (docs/DEPLOYMENT.md).

    Ephemeral *test* databases don't come through here: fixtures use
    ``Base.metadata.create_all`` for speed, and the dedicated migration
    tests prove the two paths produce the same schema.
    """
    from alembic import command
    from alembic.config import Config

    target = eng or engine
    cfg = Config(str(_ALEMBIC_INI))
    # The running process already imports the app; the ini's prepend_sys_path
    # is only for CLI invocations, and would otherwise pile a duplicate path
    # entry onto sys.path at every boot.
    cfg.set_main_option("prepend_sys_path", "")
    cfg.attributes["connection"] = target

    tables = set(inspect(target).get_table_names())
    if tables and "alembic_version" not in tables:
        command.stamp(cfg, _BASELINE_REVISION)
    command.upgrade(cfg, "head")


def get_db() -> Iterator[Session]:
    """FastAPI dependency: a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
