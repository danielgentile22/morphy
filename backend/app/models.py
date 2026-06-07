"""ORM models — tenant-shaped from Day 1 (ADR-055).

Every table carries ``tenant_id``; every query filters by it. A ``Lead``
is keyed ``(tenant_id, display_cluster_id)`` — the cross-state landowner
identity (ADR-061), never a parcel or tower id. The owners index itself
is static, read-only, and *not* per-tenant; only the lead state below is.

Identity table (Slice 2 / #48): ``User`` maps a sign-in identity to its
tenant. Table name ``app_user`` avoids the reserved ``user`` keyword on
Postgres.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .lead_status import INITIAL_STATUS


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Lead(Base):
    """One cross-state landowner's outreach state for one tenant.

    The ``contact_*`` columns (Slice 3 / #49) are the team's *editable*
    record of who they actually reach — distinct from the read-only
    mailing address served from the source parcel data.
    """

    __tablename__ = "lead"

    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_cluster_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=INITIAL_STATUS)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    contact_phone: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    best_channel: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ContactAttempt(Base):
    """An activity event for a Lead.

    Carries a ``direction`` (UI overhaul P2 / #106, ADR-066): **outbound**
    (a touch we made) or **inbound** (a *reply* the owner sent). A reply is
    simply any inbound row, logged manually now and auto-filled from Gmail
    later — the Dashboard reads "inbound events", never an email provider.
    Also receives auto-logged rows when a Lead's status transitions
    (``channel='status'``, always outbound bookkeeping — never a reply).
    """

    __tablename__ = "contact_attempt"

    # Composite indexes covering the hot read paths (PERF-006): the
    # ``ORDER BY occurred_on DESC, id DESC`` streams are served directly by an
    # index range scan instead of a TEMP B-TREE filesort. ``tenant_attempts``
    # (tenant-wide stream) uses the first; ``list_attempts`` (one owner) the
    # second. SQLite/Postgres scan ASC indexes backwards, so DESC is served.
    __table_args__ = (
        Index("ix_attempt_tenant_occurred", "tenant_id", "occurred_on", "id"),
        Index(
            "ix_attempt_tenant_cid_occurred",
            "tenant_id",
            "display_cluster_id",
            "occurred_on",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    display_cluster_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # outbound (we touched them) | inbound (they replied). Default outbound so
    # an additive migration back-fills existing rows correctly (#106).
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="outbound")
    # Who logged it — the teammate dimension for History/Stats (#112/#113);
    # nullable (auto-logged status rows + pre-#112 rows have no logger).
    logged_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class OwnerClusterOverride(Base):
    """A manual merge override (Slice 7 / #53, ADR-056).

    One row says ``source_cluster_id`` should resolve to ``target_cluster_id``
    for this tenant — the safety net when the conservative auto-clustering
    splits one landowner into several (or merges two distinct ones). Raw
    cluster ids stay untouched in the parquet/owners index; the backend
    computes ``display_cluster_id = coalesce(override_target, raw_cluster_id)``
    by following these rows, so overrides survive an owners-index recompute.

    PK ``(tenant_id, source_cluster_id)`` — a source merges into at most one
    target; a *split* simply deletes the row, returning the source to its raw
    cluster. Overrides are per-tenant (one team's merge is invisible to others).
    """

    __tablename__ = "owner_cluster_override"

    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_cluster_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_cluster_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AntennaOverride(Base):
    """Per-antenna manual state for one tenant (UI overhaul round 2).

    Towers are read-only in the owners index; this table is the team's
    *editable* layer over a single antenna (keyed by ASR), tenant-scoped
    like every other table:

    * ``archived`` parks an antenna that's been considered but isn't of
      interest — it drops out of the Explore map + list until un-archived
      (recoverable, never deleted).
    * ``address`` is a hand-entered street address (the index carries only
      coordinates).
    * the ``owner_*`` + ``notes`` columns capture details for a tower whose
      landowner we couldn't auto-resolve (an *unowned* tower) — it has no
      Lead/owner-cluster to hang them on, so they live here.

    PK ``(tenant_id, asr)`` — one row per antenna per team, created lazily on
    first edit. An antenna with no row is simply unedited (not archived). A
    brand-new table, so ``create_all`` builds it on any DB — no additive
    migration entry needed.
    """

    __tablename__ = "antenna_override"

    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asr: Mapped[str] = mapped_column(String(32), primary_key=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    address: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    owner_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    owner_phone: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    owner_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Tenant(Base):
    """A team — the unit of lead-board sharing and isolation (#86, PRD #83).

    Teams ARE tenants: every table already carries ``tenant_id``, so team
    isolation is the existing tenant isolation — no new machinery. Names are
    unique and normalized (trimmed + lowercased). Teams are find-or-created
    in credentials-file order, so the first team in the file receives id 1
    and thereby inherits the pre-teams lead board. Tenant rows are never
    deleted — a team whose users are all removed keeps its data.
    """

    __tablename__ = "tenant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Task(Base):
    """A unit of work — a follow-up, a business task, or a dev todo, all the
    same entity (UI overhaul P2 / #107, ADR-065). Tenant-scoped.

    The thin tracer ships title / description / status / creator / timestamps;
    links (owner/tower), assignee, due date, priority, labels, and source
    follow in #110. Schema changes ride the additive ``init_db`` migration.
    """

    __tablename__ = "task"

    # Serves ``list``/``list_filtered``'s ``ORDER BY created_at DESC, id DESC``
    # without a TEMP B-TREE filesort at production task counts (PERF-023).
    __table_args__ = (Index("ix_task_tenant_created", "tenant_id", "created_at", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # open | in_progress | done (see task_store.TASK_STATUSES).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    # none | low | med | high (#110).
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="none")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Optional links (#110): a Lead (owner, by display_cluster_id) and/or a
    # tower (by ASR). Either, both, or neither (a freestanding todo).
    lead_cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tower_asr: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # The assigned teammate (a tenant User), or null (unassigned).
    assignee_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Free-form labels, normalized comma-separated (e.g. "dev,outreach").
    labels: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    # manual | auto (auto-created follow-ups, #116).
    source: Mapped[str] = mapped_column(String(8), nullable=False, default="manual")
    # The User who created it (nullable — auto-created tasks #116 have no human).
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantSetting(Base):
    """A per-tenant key/value config (UI overhaul P5 / #116). Generic so new
    settings (the auto-follow-up window + on/off now; more rules later) need no
    schema change — just a new key. PK ``(tenant_id, key)``."""

    __tablename__ = "tenant_setting"

    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class UserSetting(Base):
    """A per-user key/value preference (PRD #121). The first *per-user* persisted
    preference layer in a codebase that was tenant-shaped until now — mirrors
    ``TenantSetting`` but scoped to the individual: PK ``(tenant_id, user_id,
    key)``. Generic, so new prefs slot in as new keys with no schema change.
    ``value`` is ``Text`` (not ``String(255)``) because some keys hold opaque
    client-owned JSON blobs (a saved filter snapshot, a home-view) the backend
    persists + serves without inspecting.

    A brand-new table, so ``create_all`` builds it on any DB — no additive
    migration entry needed.
    """

    __tablename__ = "user_setting"

    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")


class ScoringPreset(Base):
    """A named, tenant-shared scoring configuration (UI overhaul P4 / #115,
    ADR-058 amended). Both teammates see the same presets (the team is one
    tenant). ``config`` is an opaque JSON blob the client owns (``useDefault``
    + feature weights); the backend just persists + serves it. At most one
    ``is_default`` per tenant.
    """

    __tablename__ = "scoring_preset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class User(Base):
    """A person who can sign in, bound to exactly one tenant (= team).

    The JWT issued at sign-in carries this user's ``tenant_id``; every
    route then scopes to it. The tenant is resolved from the user's team in
    the credentials file at login (#86) and re-synced there on every login,
    so a team change in the file re-homes the user. Email (the username,
    stored opaquely) is lowercased + unique.
    """

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    # Friendly name for task assignment (#110); '' falls back to the email.
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
