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
# Deterministic auth in tests: dev posture (so the zero-config built-in
# ``dev``/``dev`` login is available) with a fixed (non-prod) signing secret.
os.environ.setdefault("AUTH_DEV_MODE", "1")
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-not-for-prod-but-long-enough-for-hs256")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from backend.app.db import Base  # noqa: E402
from backend.app.lead_store import LeadStore  # noqa: E402


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """A DB URL for the test engine.

    Defaults to **SQLite** — fast, reliable, and behaviorally equivalent
    for Slice 1, whose tenant isolation is application-level (every query
    filters by ``tenant_id``; no JSONB/FTS/RLS). Opt into real Postgres
    (TESTING.md §11.1) two ways:

    - ``PILOT_TEST_DATABASE_URL=postgresql://…`` — point at a running
      Postgres (e.g. a CI ``services: postgres`` container); or
    - ``PILOT_TEST_TESTCONTAINERS=1`` — spin one via testcontainers when a
      Docker daemon is available.

    (Auto-starting testcontainers by default was dropped: it is slow and
    flaky on the CI runner — the container starts but the run never
    settles.)
    """
    explicit = os.environ.get("PILOT_TEST_DATABASE_URL")
    if explicit:
        yield _force_psycopg3(explicit)
        return

    if os.environ.get("PILOT_TEST_TESTCONTAINERS"):
        container = None
        try:
            from testcontainers.postgres import PostgresContainer

            container = PostgresContainer("postgres:16-alpine")
            container.start()
        except Exception:  # noqa: BLE001 — no testcontainers or no Docker daemon
            container = None
        if container is not None:
            try:
                yield _force_psycopg3(container.get_connection_url())
            finally:
                container.stop()
            return

    yield "sqlite+pysqlite:///:memory:"


def _force_psycopg3(url: str) -> str:
    """testcontainers defaults to the psycopg2 driver, but we install
    psycopg (v3); rewrite the URL so SQLAlchemy loads the driver we have."""
    if "+psycopg2://" in url:
        return url.replace("+psycopg2://", "+psycopg://")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


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
