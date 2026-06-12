"""The forward-auth seam behind the edge /data gate (PRD #130).

``GET /api/auth/check`` is what Caddy's ``forward_auth`` asks before serving
any byte under ``/data/processed/*``. It validates the session (cookie first,
bearer fallback) and re-checks the username against the credentials file — so
the ADR-063 per-request authority invariant extends to the data plane: remove
a user, and their tile/parquet fetches die on the next request, JWT TTL
notwithstanding. The edge side of the contract (401 → no file bytes, 2xx →
Range/206 intact) is pinned by tests/test_caddy_serving.py against the real
Caddy binary.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

from backend.app.config import settings
from backend.app.password import hash_password

from ._helpers import api, auth_header, login

SAMPLE = {"schema_version": 1, "count": 0, "owners": []}


@contextlib.contextmanager
def extra_user(username: str, password: str, team: str = "devteam") -> Iterator[None]:
    creds = Path(settings.credentials_path)
    original = creds.read_text()
    creds.write_text(original + f"{username}:{hash_password(password)}:{team}\n")
    try:
        yield
    finally:
        creds.write_text(original)


def test_no_session_is_401() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        assert client.get("/api/auth/check").status_code == 401


def test_a_session_cookie_passes() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        client.post("/api/auth/login", json={"username": "dev", "password": "dev"})
        r = client.get("/api/auth/check")  # the jar carries the cookie
        assert r.status_code == 204
        assert r.content == b""  # no body — the edge only needs the status


def test_a_bearer_header_passes() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        token = login(client)  # clears the jar; bearer is the only credential
        assert client.get("/api/auth/check", headers=auth_header(token)).status_code == 204


def test_a_garbage_token_is_401() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        assert client.get("/api/auth/check", headers=auth_header("not.a.jwt")).status_code == 401


def test_a_removed_users_data_access_dies_on_their_next_fetch() -> None:
    # Per-request authority on the data plane: the file decides, every time.
    with api(SAMPLE) as (client, _eng, _sender):
        with extra_user("alice", "pw"):
            client.post("/api/auth/login", json={"username": "alice", "password": "pw"})
            assert client.get("/api/auth/check").status_code == 204
        # alice is out of the file — her unexpired cookie no longer unlocks data.
        assert client.get("/api/auth/check").status_code == 401
