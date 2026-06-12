"""Cookie session transport + CSRF posture (PRD #130).

The login route sets the identity-only session JWT in an httpOnly/SameSite=Lax
cookie — the SPA's transport — while ``Authorization: Bearer`` stays accepted
(tests, curl, transition); the cookie is checked first. A sign-out endpoint
clears it. With auth riding in a cookie, an Origin/Referer check on non-GET
API routes is the CSRF backstop (SameSite=Lax is the first line).

The ADR-062/063 invariants are transport-independent and re-pinned here over
the cookie path: per-request authority (a removed user's cookie dies on their
next request) and the identity-only JWT (the cookie holds the same token).
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

from backend.app.auth import SESSION_COOKIE
from backend.app.config import settings
from backend.app.password import hash_password

from ._helpers import api, auth_header

SAMPLE = {
    "schema_version": 1,
    "count": 1,
    "owners": [
        {
            "display_cluster_id": "nat0000aaaa",
            "owner_name": "AMERICAN TOWERS LLC",
            "owner_name_norm": "AMERICAN TOWERS",
            "owner_kind": "llc",
            "states": ["AR"],
            "n_states": 1,
            "cross_state": False,
            "parcel_count": 1,
            "tower_count": 3,
            "solar_count": 0,
            "total_assessed_value": 1.0,
            "max_parcel_score": 0.5,
            "score": 0.5,
            "distress_tier": "at-risk",
            "in_oz": False,
            "in_qct": False,
            "persistent_poverty": False,
        }
    ],
}

CID = "nat0000aaaa"


@contextlib.contextmanager
def extra_user(username: str, password: str, team: str = "devteam") -> Iterator[Path]:
    """Append a credential line to the test file; restore afterward."""
    creds = Path(settings.credentials_path)
    original = creds.read_text()
    creds.write_text(original + f"{username}:{hash_password(password)}:{team}\n")
    try:
        yield creds
    finally:
        creds.write_text(original)


def login_response(client, username: str = "dev", password: str = "dev"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r


# ── the login route sets the session cookie ──────────────────────────────────
def test_login_sets_an_httponly_samesite_lax_session_cookie() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        r = login_response(client)
        set_cookie = r.headers["set-cookie"].lower()
        assert SESSION_COOKIE in set_cookie
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie
        assert "path=/" in set_cookie
        assert "max-age=" in set_cookie
        # The cookie carries the same identity-only JWT the body returns —
        # one token, a second transport (PRD #130).
        assert client.cookies[SESSION_COOKIE] == r.json()["access_token"]


# ── the cookie alone authenticates ────────────────────────────────────────────
def test_the_cookie_alone_authenticates_api_requests() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        login_response(client)  # the client's jar now holds the cookie
        assert client.get("/api/auth/me").status_code == 200
        assert client.get("/api/candidates").status_code == 200
        assert client.get("/api/counts").status_code == 200


def test_the_cookie_outranks_a_bearer_header() -> None:
    # The PRD fixes the precedence: cookie first. With both present, the
    # cookie's identity wins — deterministic, never header-dependent.
    with extra_user("alice", "pw"), api(SAMPLE) as (client, _eng, _sender):
        dev_token = login_response(client, "dev", "dev").json()["access_token"]
        login_response(client, "alice", "pw")  # jar now holds alice's cookie
        me = client.get("/api/auth/me", headers=auth_header(dev_token)).json()
        assert me["email"] == "alice"


def test_bearer_is_still_accepted_without_a_cookie() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        token = login_response(client).json()["access_token"]
        client.cookies.clear()
        assert client.get("/api/auth/me").status_code == 401  # no cookie, no header
        assert client.get("/api/auth/me", headers=auth_header(token)).status_code == 200


# ── sign-out ──────────────────────────────────────────────────────────────────
def test_logout_clears_the_cookie_and_ends_the_session() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        login_response(client)
        assert client.get("/api/auth/me").status_code == 200
        r = client.post("/api/auth/logout")
        assert r.status_code == 204
        # The clearing Set-Cookie expires the session cookie in the browser.
        assert SESSION_COOKIE in r.headers.get("set-cookie", "")
        assert client.get("/api/auth/me").status_code == 401


def test_logout_without_a_session_is_harmless() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        assert client.post("/api/auth/logout").status_code == 204


# ── per-request authority survives the transport change ──────────────────────
def test_a_removed_users_cookie_dies_on_their_next_request() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        with extra_user("alice", "pw"):
            login_response(client, "alice", "pw")
            assert client.get("/api/candidates").status_code == 200
        # alice is gone from the file — her unexpired cookie is not enough.
        assert client.get("/api/candidates").status_code == 401
        assert client.get("/api/auth/me").status_code == 401


# ── CSRF: Origin/Referer check on non-GET routes ─────────────────────────────
def test_a_cross_origin_post_is_refused() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        r = client.post(
            "/api/auth/login",
            json={"username": "dev", "password": "dev"},
            headers={"Origin": "https://evil.example"},
        )
        assert r.status_code == 403


def test_a_cross_origin_put_is_refused_even_when_authenticated() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        login_response(client)
        r = client.put(
            f"/api/leads/{CID}",
            json={"status": "researching"},
            headers={"Origin": "https://evil.example"},
        )
        assert r.status_code == 403


def test_a_cross_site_referer_is_refused_when_origin_is_absent() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        r = client.post(
            "/api/auth/login",
            json={"username": "dev", "password": "dev"},
            headers={"Referer": "https://evil.example/page"},
        )
        assert r.status_code == 403


def test_a_same_origin_post_passes_the_check() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        # TestClient's base_url is http://testserver — its own Host header.
        r = client.post(
            "/api/auth/login",
            json={"username": "dev", "password": "dev"},
            headers={"Origin": "http://testserver"},
        )
        assert r.status_code == 200


def test_a_configured_dev_origin_passes_the_check() -> None:
    # The Vite dev server is cross-origin to uvicorn (the proxy rewrites Host),
    # so dev origins are allowed via cors_origins.
    with api(SAMPLE) as (client, _eng, _sender):
        r = client.post(
            "/api/auth/login",
            json={"username": "dev", "password": "dev"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert r.status_code == 200


def test_cross_origin_get_is_not_blocked() -> None:
    # The check guards mutations only — GETs are side-effect free and CORS
    # already governs what a cross-origin page can read.
    with api(SAMPLE) as (client, _eng, _sender):
        login_response(client)
        r = client.get("/api/counts", headers={"Origin": "https://evil.example"})
        assert r.status_code == 200


def test_a_request_with_neither_origin_nor_referer_passes() -> None:
    # Non-browser clients (curl, tests) send neither header and carry no
    # ambient cookie context — the whole bearer test suite rides this path.
    with api(SAMPLE) as (client, _eng, _sender):
        assert login_response(client).status_code == 200
