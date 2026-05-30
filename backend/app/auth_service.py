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

from sqlalchemy import delete, select, update
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
        ``None`` — sending nothing — when the email is outside the allowlist
        or has hit the per-email rate limit; the route still responds 200
        either way, so the endpoint can't enumerate which emails exist.
        """
        norm = _normalize_email(email)
        if settings.allowed_emails and norm not in settings.allowed_emails:
            return None
        if self._recent_token_count(norm) >= settings.link_rate_max:
            return None  # throttled: drop silently (no row, no send)

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
        self._prune_used_tokens(norm)

        base = settings.cors_origins[0] if settings.cors_origins else "http://localhost:5173"
        self.sender.send_login_link(norm, f"{base}/#/signin?token={raw}")
        return raw

    def _recent_token_count(self, email: str) -> int:
        """How many links this email got inside the rate window. Counted in
        Python (not a SQL ``created_at >= cutoff``) because SQLite stores
        naive datetimes and would mis-compare a tz-aware bound; the within-
        window rows are the newest, so a small LIMIT bounds the scan."""
        cutoff = datetime.now(UTC) - timedelta(minutes=settings.link_rate_window_minutes)
        stmt = (
            select(MagicLinkToken.created_at)
            .where(MagicLinkToken.email == email)
            .order_by(MagicLinkToken.created_at.desc())
            .limit(settings.link_rate_max + 1)
        )
        return sum(1 for created in self.session.scalars(stmt) if _aware(created) >= cutoff)

    def _prune_used_tokens(self, email: str) -> None:
        """Best-effort cleanup of this email's already-redeemed tokens, on a
        tz-free predicate (safe on SQLite + Postgres). Pruning expired-but-
        unused tokens globally is a periodic job — out of scope here."""
        self.session.execute(
            delete(MagicLinkToken).where(
                MagicLinkToken.email == email, MagicLinkToken.used_at.is_not(None)
            )
        )
        self.session.commit()

    # ── exchange → principal ────────────────────────────────────────────────
    def exchange(self, raw_token: str) -> Principal:
        """Redeem a valid token once → the Principal. Raises ``InvalidToken``
        if unknown, already used, or expired."""
        token_hash = auth.hash_token(raw_token)
        stmt = select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash)
        token = self.session.scalars(stmt).first()
        if token is None:
            raise InvalidToken("invalid or expired token")
        # Expiry never changes, so it isn't the race — check it in Python (tz-
        # safe across SQLite/Postgres) and read the Principal fields now.
        now = datetime.now(UTC)
        if _aware(token.expires_at) < now:
            raise InvalidToken("invalid or expired token")
        principal = Principal(tenant_id=token.tenant_id, user_id=token.user_id, email=token.email)

        # One-time use *is* the race. Claim the row atomically: only the row
        # still un-redeemed is updated, so concurrent redemptions can't both
        # win — the loser gets rowcount 0.
        result = self.session.execute(
            update(MagicLinkToken)
            .where(MagicLinkToken.token_hash == token_hash, MagicLinkToken.used_at.is_(None))
            .values(used_at=now)
        )
        self.session.commit()
        if result.rowcount != 1:
            raise InvalidToken("invalid or expired token")
        return principal
