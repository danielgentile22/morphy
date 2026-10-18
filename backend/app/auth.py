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
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .auth_service import NotAuthorized, Principal, resolve_principal
from .config import settings
from .db import get_db

# Where the session JWT rides (PRD #130): an httpOnly/Secure/SameSite=Lax
# cookie set by the login route. Page scripts can't read it, and it travels
# automatically on same-origin fetches (MapLibre tiles, PMTiles ranges,
# DuckDB-WASM parquet reads) — which is what lets the edge gate /data without
# any auth-header plumbing in the frontend data libraries.
SESSION_COOKIE = "morphy_session"

# HTTPBearer with auto_error off so we control the response: a missing or
# malformed credential is a 401 (not Starlette's default 403), with the
# WWW-Authenticate header the spec wants.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)

READ_ONLY_DETAIL = "This is a read-only demo account. Changes are disabled."
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


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
def session_token(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """The session JWT for this request: the cookie first (the SPA's
    transport, PRD #130), then ``Authorization: Bearer`` (tests, curl,
    transition). 401 when neither is present."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return cookie
    if creds is not None and creds.credentials:
        return creds.credentials
    raise _UNAUTHENTICATED


def current_principal(
    request: Request,
    token: str = Depends(session_token),
    db: Session = Depends(get_db),
) -> Principal:
    """Verify the session JWT (cookie or bearer), then authorize its username
    against the credential table (#88). Rejects with 401 when the token is
    invalid OR the username has no credential row anymore.

    Also the one read-only gate (ADR-077): every authenticated route resolves
    its caller here, so a read-only principal's non-GET request is refused
    with 403 before any handler runs. Sign-in/out and the demo login never
    resolve a principal, so they stay open."""
    username = decode_access_token(token)
    try:
        principal = resolve_principal(db, username)
    except NotAuthorized as exc:
        raise _UNAUTHENTICATED from exc
    if principal.read_only and request.method not in _SAFE_METHODS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=READ_ONLY_DETAIL)
    return principal


def current_tenant_id(principal: Principal = Depends(current_principal)) -> int:
    """The active tenant — resolved from the credentials file on this very
    request, never from a constant and never from the token.

    This is the seam the routes / ``get_store`` already depend on."""
    return principal.tenant_id
