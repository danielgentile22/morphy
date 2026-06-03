"""Auth primitives + the tenant-resolution seam (Slice 2 / #48, ADR-055/063).

The flow (#88 — the credentials file is authoritative on every request):

  login        → a valid username/password mints an *identity-only* JWT
                 (subject = the username; no tenant claim)
  every route  → verifies the JWT, then re-authorizes the username against
                 the credentials file: still present? which team *now*? →
                 that team's tenant scopes the request

This module holds the stateless JWT issue/verify crypto and the FastAPI
dependencies; the file-backed authorization lives in ``auth_service.py``.
``current_tenant_id`` remains the single seam the routes depend on.

Consequence: removing a user from the file (or moving their team) takes
effect on their very next request — a valid, unexpired session is proof of
identity, never of authorization.

Never log a JWT.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .auth_service import NotAuthorized, Principal, resolve_principal
from .config import settings
from .db import get_db

# HTTPBearer with auto_error off so we control the response: a missing or
# malformed credential is a 401 (not Starlette's default 403), with the
# WWW-Authenticate header the spec wants.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


# ── session JWTs (identity-only, #88) ───────────────────────────────────────
def create_access_token(username: str, *, now: datetime | None = None) -> str:
    """Issue an HS256 session JWT for ``username`` (TTL = session_ttl_days).

    The token carries identity only — no tenant, no team. Authorization is
    re-derived from the credentials file on every request, so nothing a
    token holds can grant access the file doesn't currently grant.
    """
    issued = now or datetime.now(UTC)
    payload = {
        "sub": username,
        "iat": issued,
        "exp": issued + timedelta(days=settings.session_ttl_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """Verify signature + expiry and return the username. Raises 401 on any
    failure (bad signature, expired, malformed, missing subject)."""
    try:
        # Pin the algorithm — never trust the token header's ``alg`` (guards
        # against alg-confusion / ``none`` downgrade attacks).
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        username = str(claims["sub"])
        if not username:
            raise KeyError("sub")
        return username
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise _UNAUTHENTICATED from exc


# ── FastAPI dependencies ────────────────────────────────────────────────────
def current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Principal:
    """Verify the bearer JWT, then authorize its username against the
    credentials file (#88). Rejects with 401 when the token is invalid OR
    the username has been removed from the file."""
    if creds is None or not creds.credentials:
        raise _UNAUTHENTICATED
    username = decode_access_token(creds.credentials)
    try:
        return resolve_principal(db, username)
    except NotAuthorized as exc:
        raise _UNAUTHENTICATED from exc


def current_tenant_id(principal: Principal = Depends(current_principal)) -> int:
    """The active tenant — resolved from the credentials file on this very
    request, never from a constant and never from the token.

    This is the seam the routes / ``get_store`` already depend on."""
    return principal.tenant_id
