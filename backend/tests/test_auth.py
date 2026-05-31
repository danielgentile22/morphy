"""Username/password login over HTTP (Slice 1 / #76).

Pins the externally observable auth behavior: a wrong password and an unknown
username are *distinguishable* 401s, a valid credential mints a usable JWT,
every data route rejects an unauthenticated caller, and two distinct usernames
share the one tenant. The reused JWT seam (create/decode) is checked directly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException

from backend.app.auth import Principal, create_access_token, decode_access_token
from backend.app.config import settings
from backend.app.password import hash_password

from ._helpers import api, auth_header, login

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
        assert me["tenant_id"] == settings.default_tenant_id


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


# ── two users, one tenant ─────────────────────────────────────────────────────
def test_two_usernames_share_one_tenant() -> None:
    # Seed a second credential alongside the built-in dev login (the app_users
    # dict is mutable even though Settings is frozen); restore it afterward.
    settings.app_users["alice"] = hash_password("wonderland")
    try:
        with api(SAMPLE) as (client, _eng, _sender):

            def identity(username: str, password: str) -> tuple[dict, str]:
                token = client.post(
                    "/api/auth/login", json={"username": username, "password": password}
                ).json()["access_token"]
                me = client.get("/api/auth/me", headers=auth_header(token)).json()
                return me, token

            dev_me, dev_token = identity("dev", "dev")
            alice_me, alice_token = identity("alice", "wonderland")

            # Distinct identities, one shared tenant.
            assert dev_me["email"] != alice_me["email"]
            assert dev_me["tenant_id"] == alice_me["tenant_id"] == settings.default_tenant_id

            # Same tenant → identical candidate view.
            dev_c = client.get("/api/candidates", headers=auth_header(dev_token)).json()
            alice_c = client.get("/api/candidates", headers=auth_header(alice_token)).json()
            assert dev_c == alice_c
    finally:
        settings.app_users.pop("alice", None)


# ── JWT seam (reused verbatim) ────────────────────────────────────────────────
def test_jwt_round_trip_carries_tenant_and_identity() -> None:
    principal = Principal(tenant_id=3, user_id=9, email="alice")
    decoded = decode_access_token(create_access_token(principal))
    assert (decoded.tenant_id, decoded.user_id, decoded.email) == (3, 9, "alice")


def test_expired_jwt_is_rejected() -> None:
    principal = Principal(tenant_id=1, user_id=1, email="dev")
    stale = create_access_token(principal, now=datetime.now(UTC) - timedelta(days=999))
    with pytest.raises(HTTPException) as exc:
        decode_access_token(stale)
    assert exc.value.status_code == 401


def test_tampered_jwt_is_rejected() -> None:
    forged = jwt.encode(
        {"sub": "1", "tid": 1, "email": "dev"},
        "a-different-secret-also-long-enough-for-hs256",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        decode_access_token(forged)
    assert exc.value.status_code == 401
