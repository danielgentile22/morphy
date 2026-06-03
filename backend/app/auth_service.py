"""Username/password sign-in + user provisioning (Slice 1 / #76, ADR-055).

Session-scoped like ``LeadStore``. ``login`` verifies a credential against
the credentials file (#84 — re-read on every login, so edits to the file
apply without a restart) and find-or-creates the ``User`` row (new users land
in the default tenant), returning the ``Principal`` the route turns into a
session JWT. The tenant rides on that JWT; every route then scopes to it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import credentials
from .auth import Principal
from .config import settings
from .credentials import AuthOutcome
from .models import User


class InvalidCredentials(ValueError):
    """Login failed. The message distinguishes unknown-user vs wrong-password
    (the chosen *specific*-error UX), and the route maps it to a 401."""


def login(session: Session, *, username: str, password: str) -> Principal:
    """Username/password sign-in: verify against the credentials file,
    find-or-create the ``User`` in the default tenant, and return a
    ``Principal`` the route turns into a JWT.

    Every credential shares the one default tenant (teams-as-tenants lands
    with #86); each username is its own identity, stored opaquely in
    ``User.email`` (no schema change). Raises ``InvalidCredentials`` with a
    specific message on failure.
    """
    users = credentials.load(settings.credentials_path)
    result = credentials.authenticate(users, username, password)
    if result.outcome is AuthOutcome.UNKNOWN_USER:
        raise InvalidCredentials("Unknown username")
    if result.outcome is AuthOutcome.WRONG_PASSWORD:
        raise InvalidCredentials("Incorrect password")

    user = AuthService(session).provision_user(result.username, settings.default_tenant_id)
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
        """Find-or-create a user bound to ``tenant_id`` (idempotent).

        New sign-ins go through here with the default tenant; an existing
        user keeps their tenant (we don't silently re-home them)."""
        user = self.get_user_by_email(email)
        if user is None:
            user = User(tenant_id=tenant_id, email=_normalize_email(email))
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)
        return user
