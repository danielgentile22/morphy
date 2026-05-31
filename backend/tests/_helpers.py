"""Shared HTTP-test scaffolding (not collected — no ``test_`` prefix).

``api(sample)`` yields a ``TestClient`` over a fresh in-memory SQLite DB with
a seeded owners index and the ``get_db`` dependency overridden, plus the
engine for inspection. ``login`` drives the real ``POST /api/auth/login`` with
the AUTH_DEV_MODE built-in ``dev``/``dev`` credential and returns a session
JWT, so tests authenticate exactly the way the SPA does.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app import main
from backend.app.config import settings
from backend.app.db import Base, get_db


@contextlib.contextmanager
def api(sample: dict) -> Iterator[tuple[TestClient, Engine, None]]:
    Path(settings.owners_index_path).write_text(json.dumps(sample))
    main.owners_index.reload()

    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)

    def _override_db() -> Iterator[Session]:
        db = Session(bind=eng, future=True)
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = _override_db
    try:
        with TestClient(main.app) as client:
            # 3-tuple kept for call-site stability; the 3rd slot (the magic-link
            # email sender) is unused now that login is username/password.
            yield client, eng, None
    finally:
        main.app.dependency_overrides.clear()
        eng.dispose()


def login(client: TestClient, username: str = "dev", password: str = "dev") -> str:
    """Sign in via ``POST /api/auth/login``; returns the session JWT.

    Defaults to the AUTH_DEV_MODE built-in ``dev``/``dev`` credential.
    """
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def auth_header(jwt: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt}"}
