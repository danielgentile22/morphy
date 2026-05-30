"""Magic-link request/exchange flow (Slice 2 / #48, ADR-055).

Session-scoped like ``LeadStore``. ``request_link`` provisions the user
(new users → the default tenant), stores a hashed one-time token, and
hands a delivery link to the pluggable ``EmailSender``. ``exchange``
redeems a still-valid token exactly once and returns the ``Principal`` the
caller turns into a session JWT. Reused, expired, or unknown tokens all
fail identically (no oracle).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth
from .auth import Principal
from .config import settings
from .email_sender import ConsoleEmailSender, EmailSender
from .models import MagicLinkToken, User


class InvalidToken(ValueError):
    """Raised when a magic-link token is unknown, already used, or expired."""


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _aware(dt: datetime) -> datetime:
    """Treat a tz-naive timestamp (how SQLite returns them) as UTC, so
    expiry comparisons behave identically on SQLite and Postgres."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class AuthService:
    def __init__(self, session: Session, sender: EmailSender | None = None) -> None:
        self.session = session
        self.sender = sender or ConsoleEmailSender()

    # ── provisioning ────────────────────────────────────────────────────────
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

    # ── request → token ───────────────────────────────────────────────────
    def request_link(self, email: str) -> str | None:
        """Store a hashed, one-time, expiring token and trigger a send.

        Returns the raw token (the route exposes it only in dev). Returns
        ``None`` — sending nothing — for an email outside the allowlist;
        the route still responds 200 so the endpoint can't be used to
        enumerate which emails exist.
        """
        norm = _normalize_email(email)
        if settings.allowed_emails and norm not in settings.allowed_emails:
            return None

        user = self.provision_user(norm, settings.default_tenant_id)
        raw = auth.generate_token()
        self.session.add(
            MagicLinkToken(
                tenant_id=user.tenant_id,
                user_id=user.id,
                email=norm,
                token_hash=auth.hash_token(raw),
                expires_at=datetime.now(UTC) + timedelta(minutes=settings.link_ttl_minutes),
            )
        )
        self.session.commit()

        base = settings.cors_origins[0] if settings.cors_origins else "http://localhost:5173"
        self.sender.send_login_link(norm, f"{base}/#/signin?token={raw}")
        return raw

    # ── exchange → principal ────────────────────────────────────────────────
    def exchange(self, raw_token: str) -> Principal:
        """Redeem a valid token once → the Principal. Raises ``InvalidToken``
        if unknown, already used, or expired."""
        token_hash = auth.hash_token(raw_token)
        stmt = select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash)
        token = self.session.scalars(stmt).first()
        if token is None or token.used_at is not None:
            raise InvalidToken("invalid or expired token")
        if _aware(token.expires_at) < datetime.now(UTC):
            raise InvalidToken("invalid or expired token")

        token.used_at = datetime.now(UTC)
        self.session.commit()
        return Principal(tenant_id=token.tenant_id, user_id=token.user_id, email=token.email)
