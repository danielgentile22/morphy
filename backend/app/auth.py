"""Auth primitives + the tenant-resolution seam (Slice 2 / #48, ADR-055).

Replaces Slice 1's hardcoded ``tenant_id=1``. The flow is:

  login        → a valid username/password mints a short-lived JWT
  every route  → resolves the tenant from ``Authorization: Bearer <jwt>``

This module holds the stateless JWT issue/verify crypto and the FastAPI
dependencies; the DB-backed sign-in flow lives in ``auth_service.py``.
``current_tenant_id`` is the single seam the routes already depend on — it
now derives the tenant from the verified JWT instead of returning a constant.

Never log a JWT.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

# HTTPBearer with auto_error off so we control the response: a missing or
# malformed credential is a 401 (not Starlette's default 403), with the
# WWW-Authenticate header the spec wants.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, decoded from a valid session JWT."""

    tenant_id: int
    user_id: int
    email: str


# ── session JWTs ────────────────────────────────────────────────────────────
def create_access_token(principal: Principal, *, now: datetime | None = None) -> str:
    """Issue an HS256 session JWT for ``principal`` (TTL = session_ttl_days)."""
    issued = now or datetime.now(UTC)
    payload = {
        "sub": str(principal.user_id),
        "tid": principal.tenant_id,
        "email": principal.email,
        "iat": issued,
        "exp": issued + timedelta(days=settings.session_ttl_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Principal:
    """Verify signature + expiry and return the Principal. Raises 401 on
    any failure (bad signature, expired, malformed, missing claims)."""
    try:
        # Pin the algorithm — never trust the token header's ``alg`` (guards
        # against alg-confusion / ``none`` downgrade attacks).
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return Principal(
            tenant_id=int(claims["tid"]),
            user_id=int(claims["sub"]),
            email=str(claims["email"]),
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise _UNAUTHENTICATED from exc


# ── FastAPI dependencies ────────────────────────────────────────────────────
def current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    """Resolve + verify the bearer JWT, or reject the request with 401."""
    if creds is None or not creds.credentials:
        raise _UNAUTHENTICATED
    return decode_access_token(creds.credentials)


def current_tenant_id(principal: Principal = Depends(current_principal)) -> int:
    """The active tenant — derived from the JWT, never a constant.

    This is the seam the routes / ``get_store`` already depend on; swapping
    the Slice 1 stub for this is the whole tenant-isolation change."""
    return principal.tenant_id
