"""Username/password sign-in + user provisioning (Slice 1 / #76, ADR-055).

Session-scoped like ``LeadStore``. ``login`` verifies a credential against
the credentials file (#84 — re-read on every login, so edits to the file
apply without a restart), registers every team from the file in file order
and resolves the user's team to its tenant (#86 — teams are tenants), then
find-or-creates the ``User`` row synced to that tenant, returning the
``Principal`` the route turns into a session JWT. The tenant rides on that
JWT; every route then scopes to it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import credentials
from .auth import Principal
from .config import settings
from .credentials import AuthOutcome
from .models import User
from .tenant_service import TenantService


class InvalidCredentials(ValueError):
    """Login failed. The message distinguishes unknown-user vs wrong-password
    (the chosen *specific*-error UX), and the route maps it to a 401."""


def login(session: Session, *, username: str, password: str) -> Principal:
    """Username/password sign-in: verify against the credentials file,
    resolve the user's team to its tenant, sync the ``User`` row to it, and
    return a ``Principal`` the route turns into a JWT.

    Teams register find-or-create in **file order** on every login, so the
    first team in the file always owns tenant 1 (the pre-teams board).
    Each username is its own identity, stored opaquely in ``User.email``.
    Raises ``InvalidCredentials`` with a specific message on failure.
    """
    users = credentials.load(settings.credentials_path)
    result = credentials.authenticate(users, username, password)
    if result.outcome is AuthOutcome.UNKNOWN_USER:
        raise InvalidCredentials("Unknown username")
    if result.outcome is AuthOutcome.WRONG_PASSWORD:
        raise InvalidCredentials("Incorrect password")

    tenants = TenantService(session).register_teams(credentials.teams_in_file_order(users))
    tenant = tenants[result.team]
    user = AuthService(session).provision_user(result.username, tenant.id)
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

        The credentials file is the source of truth for team membership
        (#86): moving a user to another team there re-homes them here on
        their next login. Their old team's data is untouched.
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
