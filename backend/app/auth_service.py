"""Sign-in + per-request authorization against the credentials file.

Two entry points, both keyed on the same mtime-cached ``CredentialsFile``:

``login``
    Username/password sign-in (#76/#84): verify against the file, register
    every team from it in file order (#86 — the first team in the file owns
    tenant 1), sync the ``User`` row to the user's team, and return the
    ``Principal`` whose username the route turns into an identity-only JWT.

``resolve_principal``
    Per-request authorization (#88): the JWT proved *who* is calling;
    this decides whether they are *still* allowed in (present in the file)
    and which team's board they operate on *now* (their current team in the
    file). Removing a user or changing their team therefore takes effect on
    their very next request — no session wait-out, no restart.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import credentials
from .config import settings
from .credentials import AuthOutcome, CredentialEntry
from .models import User
from .tenant_service import TenantService

# The one per-process view of the credentials file. Mtime-cached: an
# unchanged file costs a stat per access, never a re-parse.
_credentials_file = credentials.CredentialsFile(settings.credentials_path)


class InvalidCredentials(ValueError):
    """Login failed. The message distinguishes unknown-user vs wrong-password
    (the chosen *specific*-error UX), and the route maps it to a 401."""


class NotAuthorized(ValueError):
    """A request-time authorization failure (#88): the session's username is
    no longer in the credentials file. The route maps it to a 401."""


@dataclass(frozen=True)
class Principal:
    """The authenticated caller.

    Identity (``email`` = the username) comes from the verified JWT;
    authorization (``tenant_id``) is resolved from the credentials file +
    DB on the request being served — never from the token (#88).
    """

    tenant_id: int
    user_id: int
    email: str


def login(session: Session, *, username: str, password: str) -> Principal:
    """Username/password sign-in. Raises ``InvalidCredentials`` on failure."""
    users = _credentials_file.current()
    result = credentials.authenticate(users, username, password)
    if result.outcome is AuthOutcome.UNKNOWN_USER:
        raise InvalidCredentials("Unknown username")
    if result.outcome is AuthOutcome.WRONG_PASSWORD:
        raise InvalidCredentials("Incorrect password")
    assert result.username is not None and result.team is not None
    return _principal_for(session, users, result.username, result.team)


def resolve_principal(session: Session, username: str) -> Principal:
    """Authorize ``username`` for this request — the file is authoritative.

    Raises ``NotAuthorized`` if the username is no longer in the file
    (revocation is effective on the next request, not at session expiry).
    """
    users = _credentials_file.current()
    entry = users.get(credentials.normalize(username))
    if entry is None:
        raise NotAuthorized("no longer authorized")
    return _principal_for(session, users, entry.username, entry.team)


def _principal_for(
    session: Session,
    users: dict[str, CredentialEntry],
    username: str,
    team: str,
) -> Principal:
    """Resolve team → tenant (file-order registration) + sync the User row."""
    tenant_svc = TenantService(session)
    tenant = tenant_svc.get_by_name(team)
    if tenant is None:
        # A team we haven't seen yet — register *all* teams in file order so
        # id assignment stays file-ordered (the first team must own tenant 1).
        tenant = tenant_svc.register_teams(credentials.teams_in_file_order(users))[team]
    user = AuthService(session).provision_user(username, tenant.id)
    return Principal(tenant_id=user.tenant_id, user_id=user.id, email=user.email)


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

        The credentials file is the source of truth for team membership:
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
