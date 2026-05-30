"""Shared HTTP-test scaffolding (not collected — no ``test_`` prefix).

``api(sample)`` yields a ``TestClient`` over a fresh in-memory SQLite DB
with a seeded owners index, the ``get_db`` + email-sender dependencies
overridden, plus the engine + recording sender for inspection. ``login``
drives the real request-link → exchange flow and returns a session JWT, so
tests authenticate exactly the way the SPA does.
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
from backend.app.email_sender import RecordingEmailSender


@contextlib.contextmanager
def api(sample: dict) -> Iterator[tuple[TestClient, Engine, RecordingEmailSender]]:
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

    sender = RecordingEmailSender()
    main.app.dependency_overrides[get_db] = _override_db
    main.app.dependency_overrides[main.get_email_sender] = lambda: sender
    try:
        with TestClient(main.app) as client:
            yield client, eng, sender
    finally:
        main.app.dependency_overrides.clear()
        eng.dispose()


def login(client: TestClient, email: str = "dev@example.com") -> str:
    """Full request-link → exchange; returns the session JWT."""
    r = client.post("/api/auth/request-link", json={"email": email})
    r.raise_for_status()
    token = r.json()["dev_token"]
    assert token, "AUTH_EXPOSE_TOKEN must be on in tests"
    r2 = client.post("/api/auth/exchange", json={"token": token})
    r2.raise_for_status()
    return r2.json()["access_token"]


def auth_header(jwt: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt}"}
