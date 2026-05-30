"""ORM models — tenant-shaped from Day 1 (ADR-055).

Every table carries ``tenant_id``; every query filters by it. A ``Lead``
is keyed ``(tenant_id, display_cluster_id)`` — the cross-state landowner
identity (ADR-061), never a parcel or tower id. The owners index itself
is static, read-only, and *not* per-tenant; only the lead state below is.

Identity tables (Slice 2 / #48): ``User`` maps an email to its tenant;
``MagicLinkToken`` holds hashed, one-time, expiring sign-in tokens (the
raw token is never persisted). Table name ``app_user`` avoids the
reserved ``user`` keyword on Postgres.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .lead_status import INITIAL_STATUS


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Lead(Base):
    """One cross-state landowner's outreach state for one tenant."""

    __tablename__ = "lead"

    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_cluster_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=INITIAL_STATUS)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ContactAttempt(Base):
    """An outreach event for a Lead.

    Also receives auto-logged rows when a Lead's status transitions
    (``channel='status'``); manual attempts are fleshed out in a later
    Lead-page slice.
    """

    __tablename__ = "contact_attempt"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    display_cluster_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class User(Base):
    """A person who can sign in, bound to exactly one tenant.

    The JWT issued at sign-in carries this user's ``tenant_id``; every
    route then scopes to it. New users are provisioned into the default
    tenant (ADR-055's "reads 1 for now"); adding a second tenant is a
    row add. Email is stored lowercased + unique.
    """

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MagicLinkToken(Base):
    """A one-time, expiring sign-in token.

    Only the SHA-256 hash of the token is stored — the raw token lives
    only in the emailed link. One-time use is enforced by ``used_at``
    (null until redeemed); ``expires_at`` bounds the window.
    """

    __tablename__ = "magic_link_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
