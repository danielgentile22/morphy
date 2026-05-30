"""Magic-link auth: token hashing/one-time/expiry, exchange, route guards.

Service-level tests inspect the stored token directly (proving it's hashed,
expiring, one-time); JWT tests round-trip the session token; route tests
prove every data route rejects an unauthenticated request and accepts a
valid JWT resolving to the right tenant.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.app import auth
from backend.app.auth import (
    Principal,
    create_access_token,
    decode_access_token,
    hash_token,
)
from backend.app.auth_service import AuthService, InvalidToken
from backend.app.config import settings
from backend.app.models import MagicLinkToken

from ._helpers import api, auth_header, login

EMAIL = "owner@example.com"

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


# ── request_link ────────────────────────────────────────────────────────────
def test_request_link_stores_hashed_expiring_token_and_sends(
    auth_service: AuthService, recording_sender
) -> None:
    raw = auth_service.request_link(EMAIL)
    assert raw  # the raw token is returned to the caller (echoed only in dev)

    rows = list(auth_service.session.scalars(select(MagicLinkToken)))
    assert len(rows) == 1
    token = rows[0]

    # hashed at rest — the raw token is nowhere in the row
    assert token.token_hash == hash_token(raw)
    assert token.token_hash != raw
    # expiring, in the future, and bounded by the configured TTL
    assert token.used_at is None
    expires = (
        token.expires_at.replace(tzinfo=UTC)
        if token.expires_at.tzinfo is None
        else token.expires_at
    )
    delta = expires - datetime.now(UTC)
    assert timedelta(0) < delta <= timedelta(minutes=settings.link_ttl_minutes + 1)

    # the sender was triggered with a link carrying the raw token
    assert len(recording_sender.sent) == 1
    sent_email, link = recording_sender.sent[0]
    assert sent_email == EMAIL
    assert raw in link


def test_request_link_normalizes_email(auth_service: AuthService) -> None:
    auth_service.request_link("  Owner@Example.COM ")
    user = auth_service.get_user_by_email(EMAIL)
    assert user is not None and user.email == EMAIL
    assert user.tenant_id == settings.default_tenant_id


# ── exchange ────────────────────────────────────────────────────────────────
def test_exchange_valid_token_returns_principal_for_right_tenant(
    auth_service: AuthService,
) -> None:
    raw = auth_service.request_link(EMAIL)
    principal = auth_service.exchange(raw)
    assert principal.tenant_id == settings.default_tenant_id
    assert principal.email == EMAIL


def test_exchange_is_one_time(auth_service: AuthService) -> None:
    raw = auth_service.request_link(EMAIL)
    auth_service.exchange(raw)  # first use succeeds
    with pytest.raises(InvalidToken):
        auth_service.exchange(raw)  # reuse fails


def test_exchange_expired_token_fails(auth_service: AuthService) -> None:
    raw = auth_service.request_link(EMAIL)
    # Backdate the stored token past its expiry.
    token = auth_service.session.scalars(
        select(MagicLinkToken).where(MagicLinkToken.token_hash == hash_token(raw))
    ).one()
    token.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    auth_service.session.commit()

    with pytest.raises(InvalidToken):
        auth_service.exchange(raw)


def test_exchange_unknown_token_fails(auth_service: AuthService) -> None:
    with pytest.raises(InvalidToken):
        auth_service.exchange("not-a-real-token")


def test_allowlist_blocks_unlisted_email(monkeypatch, auth_service: AuthService) -> None:
    # Settings is a frozen dataclass — patch the module binding with a copy.
    patched = replace(settings, allowed_emails=frozenset({"allowed@example.com"}))
    monkeypatch.setattr("backend.app.auth_service.settings", patched)
    # An unlisted email: no token stored, nothing sent, generic None return.
    assert auth_service.request_link("stranger@example.com") is None
    assert list(auth_service.session.scalars(select(MagicLinkToken))) == []


# ── JWT mechanics ───────────────────────────────────────────────────────────
def test_jwt_round_trip_carries_tenant_and_email() -> None:
    principal = Principal(tenant_id=3, user_id=9, email="x@y.com")
    decoded = decode_access_token(create_access_token(principal))
    assert (decoded.tenant_id, decoded.user_id, decoded.email) == (3, 9, "x@y.com")


def test_expired_jwt_is_rejected() -> None:
    principal = Principal(tenant_id=1, user_id=1, email="x@y.com")
    stale = create_access_token(principal, now=datetime.now(UTC) - timedelta(days=999))
    with pytest.raises(HTTPException) as exc:
        decode_access_token(stale)
    assert exc.value.status_code == 401


def test_tampered_jwt_is_rejected() -> None:
    forged = jwt.encode(
        {"sub": "1", "tid": 1, "email": "x@y.com"},
        "a-different-secret-also-long-enough-for-hs256",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        decode_access_token(forged)
    assert exc.value.status_code == 401


# ── route guards ────────────────────────────────────────────────────────────
def test_data_routes_reject_unauthenticated_requests() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        assert client.get("/api/candidates").status_code == 401
        assert client.get("/api/leads/nat0000aaaa").status_code == 401
        assert (
            client.put("/api/leads/nat0000aaaa", json={"status": "researching"}).status_code == 401
        )
        assert client.get("/api/auth/me").status_code == 401


def test_data_routes_accept_a_valid_jwt() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        headers = auth_header(login(client))
        assert client.get("/api/candidates", headers=headers).status_code == 200
        me = client.get("/api/auth/me", headers=headers).json()
        assert me["tenant_id"] == settings.default_tenant_id
        assert me["email"] == "dev@example.com"


def test_malformed_bearer_is_rejected() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        bad = {"Authorization": "Bearer not.a.jwt"}
        assert client.get("/api/candidates", headers=bad).status_code == 401


def test_health_is_public() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        assert client.get("/api/health").status_code == 200
