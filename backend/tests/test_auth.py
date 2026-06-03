"""Username/password login over HTTP (Slice 1 / #76, credentials file #84).

Pins the externally observable auth behavior: a wrong password and an unknown
username are *distinguishable* 401s, a valid credential mints a usable JWT,
every data route rejects an unauthenticated caller, the credentials file is
the live credential source (a user added to it can sign in without a restart),
and two distinct usernames share the one tenant (until teams land, #86). The
reused JWT seam (create/decode) is checked directly.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from fastapi import HTTPException

from backend.app import main
from backend.app.auth import create_access_token, decode_access_token
from backend.app.config import settings
from backend.app.login_throttle import LoginThrottle
from backend.app.password import hash_password

from ._helpers import FakeClock, api, auth_header, login

# A tiny owners index so the data routes resolve (one owner, status New).
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


# ── login route ───────────────────────────────────────────────────────────────
def test_wrong_password_is_a_specific_401() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        r = client.post("/api/auth/login", json={"username": "dev", "password": "nope"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Incorrect password"


def test_unknown_username_is_a_specific_401() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        r = client.post("/api/auth/login", json={"username": "ghost", "password": "x"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Unknown username"


def test_valid_credentials_return_a_jwt_and_grant_access() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        r = client.post("/api/auth/login", json={"username": "dev", "password": "dev"})
        assert r.status_code == 200
        body = r.json()
        assert body["access_token"]
        assert body["expires_in"] > 0  # ~30 days, in seconds

        headers = auth_header(body["access_token"])
        assert client.get("/api/candidates", headers=headers).status_code == 200
        me = client.get("/api/auth/me", headers=headers).json()
        assert me["email"] == "dev"  # the username is the opaque identity
        # dev's team is the first (only) team in the conftest-seeded file →
        # it registers as tenant 1 (#86).
        assert me["tenant_id"] == 1


def test_username_is_case_insensitive_and_trimmed() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        r = client.post("/api/auth/login", json={"username": "  DEV  ", "password": "dev"})
        assert r.status_code == 200


# ── route guards ──────────────────────────────────────────────────────────────
def test_data_routes_reject_unauthenticated_requests() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        assert client.get("/api/candidates").status_code == 401
        assert client.get("/api/my-leads").status_code == 401
        assert client.get("/api/counts").status_code == 401
        assert client.get("/api/auth/me").status_code == 401


def test_login_helper_grants_access() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        assert client.get("/api/candidates", headers=auth_header(login(client))).status_code == 200


def test_malformed_bearer_is_rejected() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        bad = {"Authorization": "Bearer not.a.jwt"}
        assert client.get("/api/candidates", headers=bad).status_code == 401


def test_health_is_public() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        assert client.get("/api/health").status_code == 200


# ── brute-force throttle (#77) ────────────────────────────────────────────────
def test_login_throttle_trips_then_recovers() -> None:
    clock = FakeClock()
    throttle = LoginThrottle(max_failures=3, window_seconds=60.0, clock=clock)
    with api(SAMPLE) as (client, _eng, _sender):
        main._login_throttle = throttle  # api() restores the original afterward
        bad = {"username": "dev", "password": "nope"}
        for _ in range(3):  # N failures are 401s, not yet throttled
            assert client.post("/api/auth/login", json=bad).status_code == 401
        # Over the limit → 429; even a *correct* password is refused while blocked.
        assert client.post("/api/auth/login", json=bad).status_code == 429
        blocked = client.post("/api/auth/login", json={"username": "dev", "password": "dev"})
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers
        # Window rolls forward → the block self-clears (no hard lockout).
        clock.advance(61)
        ok = client.post("/api/auth/login", json={"username": "dev", "password": "dev"})
        assert ok.status_code == 200
        assert ok.json()["access_token"]


def test_throttle_keys_are_independent_by_username() -> None:
    clock = FakeClock()
    throttle = LoginThrottle(max_failures=2, window_seconds=60.0, clock=clock)
    with api(SAMPLE) as (client, _eng, _sender):
        main._login_throttle = throttle  # api() restores the original afterward
        for _ in range(2):
            client.post("/api/auth/login", json={"username": "dev", "password": "nope"})
        # 'dev' is now blocked from this client...
        assert (
            client.post("/api/auth/login", json={"username": "dev", "password": "dev"}).status_code
            == 429
        )
        # ...but a different username from the same client is unaffected
        # (unknown user → 401, not throttled).
        assert (
            client.post("/api/auth/login", json={"username": "ghost", "password": "x"}).status_code
            == 401
        )


def test_successful_login_resets_the_throttle() -> None:
    clock = FakeClock()
    throttle = LoginThrottle(max_failures=3, window_seconds=60.0, clock=clock)
    with api(SAMPLE) as (client, _eng, _sender):
        main._login_throttle = throttle  # api() restores the original afterward
        for _ in range(2):  # two failures, still under the limit of 3
            client.post("/api/auth/login", json={"username": "dev", "password": "nope"})
        # A correct password succeeds and clears the counter...
        assert (
            client.post("/api/auth/login", json={"username": "dev", "password": "dev"}).status_code
            == 200
        )
        # ...so the next two failures don't immediately trip the limit.
        for _ in range(2):
            assert (
                client.post(
                    "/api/auth/login", json={"username": "dev", "password": "nope"}
                ).status_code
                == 401
            )


# ── the credentials file is the live credential source (#84) ─────────────────
@contextlib.contextmanager
def extra_user(username: str, password: str, team: str = "devteam") -> Iterator[None]:
    """Append a credential line to the file and remove it afterward. Login
    re-reads the file, so the new user is signable-in immediately."""
    creds = Path(settings.credentials_path)
    original = creds.read_text()
    creds.write_text(original + f"{username}:{hash_password(password)}:{team}\n")
    try:
        yield
    finally:
        creds.write_text(original)


def test_a_user_added_to_the_file_can_sign_in_without_restart() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        # Not in the file yet → the specific unknown-username 401.
        r = client.post("/api/auth/login", json={"username": "alice", "password": "wonderland"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Unknown username"
        # Added to the file → signs in on the very next attempt (no restart).
        with extra_user("alice", "wonderland"):
            r = client.post("/api/auth/login", json={"username": "alice", "password": "wonderland"})
            assert r.status_code == 200
        # Removed from the file → back to unknown-username on new logins.
        r = client.post("/api/auth/login", json={"username": "alice", "password": "wonderland"})
        assert r.status_code == 401


def test_two_usernames_share_one_tenant() -> None:
    # Two usernames on the same team (extra_user defaults to dev's "devteam")
    # share one tenant — the teams-as-tenants board sharing (#86).
    with extra_user("alice", "wonderland"), api(SAMPLE) as (client, _eng, _sender):

        def identity(username: str, password: str) -> tuple[dict, str]:
            token = client.post(
                "/api/auth/login", json={"username": username, "password": password}
            ).json()["access_token"]
            me = client.get("/api/auth/me", headers=auth_header(token)).json()
            return me, token

        dev_me, dev_jwt = identity("dev", "dev")
        alice_me, alice_jwt = identity("alice", "wonderland")

        # Distinct identities, one shared tenant.
        assert dev_me["email"] != alice_me["email"]
        assert dev_me["tenant_id"] == alice_me["tenant_id"] == 1

        # Same tenant → identical candidate view.
        dev_c = client.get("/api/candidates", headers=auth_header(dev_jwt)).json()
        alice_c = client.get("/api/candidates", headers=auth_header(alice_jwt)).json()
        assert dev_c == alice_c


# ── JWT seam (identity-only, #88) ─────────────────────────────────────────────
def test_jwt_round_trip_carries_identity_only() -> None:
    # The token's subject is the username — the only claim of substance.
    # Tenancy is never in the token; it's resolved from the file per request.
    assert decode_access_token(create_access_token("alice")) == "alice"


def test_expired_jwt_is_rejected() -> None:
    stale = create_access_token("dev", now=datetime.now(UTC) - timedelta(days=999))
    with pytest.raises(HTTPException) as exc:
        decode_access_token(stale)
    assert exc.value.status_code == 401


def test_tampered_jwt_is_rejected() -> None:
    forged = jwt.encode(
        {"sub": "dev"},
        "a-different-secret-also-long-enough-for-hs256",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        decode_access_token(forged)
    assert exc.value.status_code == 401
