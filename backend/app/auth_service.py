"""Sign-in + per-request authorization against the credential table.

Two entry points, both reading the DB-backed ``credentials_store`` (PRD #130
— the storage successor to the ADR-063 credentials file; the authority
invariants are unchanged):

``login``
    Username/password sign-in (#76/#84): verify against the store, register
    every team from it in registration order (#86 — the first team owns
    tenant 1), sync the ``User`` row to the user's team, and return the
    ``Principal`` whose username the route turns into an identity-only JWT.

``resolve_principal``
    Per-request authorization (#88): the JWT proved *who* is calling;
    this decides whether they are *still* allowed in (a credential row
    exists) and which team's board they operate on *now* (their current
    team in the table). Removing a user or changing their team therefore
    takes effect on their very next request — no session wait-out, no
    restart.

Cost per authenticated request: three indexed SELECTs (credential, tenant by
name, user by email) — negligible at this product's scale (ADR-063 said the
same of the file's stat + two SELECTs; the PERF-025 memo retired with the
file, whose mtime was its invalidation signal).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import credentials_store
from .credentials import AuthOutcome, CredentialEntry
from .models import User
from .tenant_service import TenantService


class InvalidCredentials(ValueError):
    """Login failed. The message distinguishes unknown-user vs wrong-password
    (the chosen *specific*-error UX), and the route maps it to a 401."""


class NotAuthorized(ValueError):
    """A request-time authorization failure (#88): the session's username has
    no credential row anymore. The route maps it to a 401."""


@dataclass(frozen=True)
class Principal:
    """The authenticated caller.

    Identity (``email`` = the username) comes from the verified JWT;
    authorization (``tenant_id``) is resolved from the credential table +
    DB on the request being served — never from the token (#88).
    """

    tenant_id: int
    user_id: int
    email: str
    # From the credential row on this request, like the tenant (ADR-077): a
    # read-only principal's non-GET requests are refused in ``current_principal``.
    read_only: bool


def login(session: Session, *, username: str, password: str) -> Principal:
    """Username/password sign-in. Raises ``InvalidCredentials`` on failure."""
    result = credentials_store.authenticate(session, username, password)
    if result.outcome is AuthOutcome.UNKNOWN_USER:
        raise InvalidCredentials("Unknown username")
    if result.outcome is AuthOutcome.WRONG_PASSWORD:
        raise InvalidCredentials("Incorrect password")
    assert result.username is not None
    return resolve_principal(session, result.username)


def is_authorized(session: Session, username: str) -> bool:
    """Credential-presence check only — the data-plane forward-auth seam
    (PRD #130). The edge asks this on every ``/data/processed/*`` fetch
    (tiles, parquet ranges — bursts of requests): identity came from the
    verified JWT, and a credential row is the whole of the per-request
    authority invariant. Removing a user gates their data access on their
    very next fetch, same as the API routes."""
    return credentials_store.get(session, username) is not None


def resolve_principal(session: Session, username: str) -> Principal:
    """Authorize ``username`` for this request — the credential table is
    authoritative.

    Raises ``NotAuthorized`` if the username has no credential row anymore
    (revocation is effective on the next request, not at session expiry).
    """
    entry = credentials_store.get(session, username)
    if entry is None:
        raise NotAuthorized("no longer authorized")
    return _principal_for(session, entry)


def _principal_for(session: Session, entry: CredentialEntry) -> Principal:
    """Resolve team → tenant (registration-order semantics) + sync the User row."""
    tenant_svc = TenantService(session)
    tenant = tenant_svc.get_by_name(entry.team)
    if tenant is None:
        # A team we haven't seen yet — register *all* teams in credential
        # order so id assignment stays registration-ordered (the first team
        # must own tenant 1).
        tenant = tenant_svc.register_teams(credentials_store.teams_in_order(session))[entry.team]
    user = AuthService(session).provision_user(entry.username, tenant.id)
    return Principal(
        tenant_id=user.tenant_id, user_id=user.id, email=user.email, read_only=entry.read_only
    )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == _normalize_email(email))
        return self.session.scalars(stmt).first()

    def provision_user(self, email: str, tenant_id: int) -> User:
        """Find-or-create a user bound to ``tenant_id``, syncing an existing
        user's tenant when it differs (idempotent).

        The credential table is the source of truth for team membership:
        moving a user to another team there re-homes them here on their next
        login or request. Their old team's data is untouched.
        """
        user = self.get_user_by_email(email)
        if user is None:
            user = User(tenant_id=tenant_id, email=_normalize_email(email))
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)
        elif user.tenant_id != tenant_id:
            user.tenant_id = tenant_id
            self.session.commit()
            self.session.refresh(user)
        return user
