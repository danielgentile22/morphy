"""Backend test fixtures.

Database fixture (TESTING.md §11.1): prefer a real Postgres — an explicit
``PILOT_TEST_DATABASE_URL`` or a testcontainers Postgres when Docker is
available — and fall back to SQLite when neither is present. Slice 1's
tenant isolation is enforced in application code (every query filters by
``tenant_id``, no dialect-specific JSONB/FTS/RLS), so the SQLite fallback
exercises the same behavior and keeps the suite green without Docker.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterator

import pytest

# Point the app's *default* engine + owners index at throwaway temp paths
# before any backend module imports config — so importing the FastAPI app
# (for the API test) never touches the real dev DB or owners_index.json.
_TMP = tempfile.mkdtemp(prefix="pilot-leadtest-")
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{_TMP}/lead_state.sqlite3")
os.environ.setdefault("OWNERS_INDEX_PATH", f"{_TMP}/owners_index.json")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from backend.app.db import Base  # noqa: E402
from backend.app.lead_store import LeadStore  # noqa: E402


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """A DB URL for the test engine: Postgres if reachable, else SQLite."""
    explicit = os.environ.get("PILOT_TEST_DATABASE_URL")
    if explicit:
        yield explicit
        return

    container = None
    try:  # testcontainers + Docker — the TESTING.md §11.1 path
        from testcontainers.postgres import PostgresContainer

        container = PostgresContainer("postgres:16-alpine")
        container.start()
    except Exception:  # noqa: BLE001 — no testcontainers or no Docker daemon
        container = None

    if container is not None:
        try:
            yield container.get_connection_url()
        finally:
            container.stop()
    else:  # Docker-free fallback (e.g. local dev without a daemon)
        yield "sqlite+pysqlite:///:memory:"


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    """A fresh schema per test. In-memory SQLite shares one connection
    (StaticPool) so multiple Sessions in a test see the same data."""
    kwargs: dict = {"future": True}
    if database_url.startswith("sqlite") and ":memory:" in database_url:
        kwargs.update(connect_args={"check_same_thread": False}, poolclass=StaticPool)
    eng = create_engine(database_url, **kwargs)
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture
def new_session(engine: Engine) -> Callable[[], Session]:
    """Factory for fresh sessions on the test engine (to simulate reloads
    and cross-session reads)."""

    def _make() -> Session:
        return Session(bind=engine, future=True)

    return _make


@pytest.fixture
def store_factory(new_session: Callable[[], Session]) -> Callable[[int], LeadStore]:
    """Factory for a tenant-scoped LeadStore on its own session."""

    def _make(tenant_id: int) -> LeadStore:
        return LeadStore(new_session(), tenant_id)

    return _make
