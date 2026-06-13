"""Tenant-scoped persistence for Tasks (UI overhaul P2 / #107, ADR-065).

A Task is a unit of work — a follow-up, a business task, or a dev todo, all
the same entity (CONTEXT.md). This is the thin tracer: create / list / read /
update-status / delete, every method filtered by ``self.tenant_id`` (the
multi-tenant isolation chokepoint, like ``LeadStore``). Links, assignee, due
date, priority, labels, filtering, and free-text search land in #110.
"""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime
from typing import cast

from sqlalchemy import CursorResult, delete, func, or_, select
from sqlalchemy.orm import Session

from .models import Task


class _Sentinel(enum.Enum):
    """Single-member sentinel for ``TaskStore.update``: distinguishes "omit
    this field" (leave it unchanged) from passing ``None`` (clear a nullable
    link/assignee/due field). A one-member Enum is the type-checker-narrowable
    sentinel idiom — ``x is not _UNSET`` narrows ``x`` to its real type."""

    UNSET = enum.auto()


_UNSET = _Sentinel.UNSET

# A Task's lifecycle status. No ladder — any status may move to any other
# (you can reopen a done task); reaching ``done`` stamps ``completed_at``.
TASK_STATUSES: tuple[str, ...] = ("open", "in_progress", "done")
INITIAL_TASK_STATUS = "open"
DONE_STATUS = "done"

TASK_PRIORITIES: tuple[str, ...] = ("none", "low", "med", "high")


class InvalidTaskStatus(ValueError):
    """Raised when a task status is not one of ``TASK_STATUSES``."""


class InvalidTaskPriority(ValueError):
    """Raised when a task priority is not one of ``TASK_PRIORITIES``."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_labels(raw: str | list[str] | None) -> str:
    """Normalize free-form labels to a stable comma-separated string
    (trimmed, lowercased, de-duped, order-preserving). '' when none."""
    if raw is None:
        return ""
    parts = raw.split(",") if isinstance(raw, str) else list(raw)
    out: list[str] = []
    for p in parts:
        label = str(p).strip().lower()
        if label and label not in out:
            out.append(label)
    return ",".join(out)


def label_list(labels: str) -> list[str]:
    return [x for x in labels.split(",") if x]


class TaskStore:
    def __init__(self, session: Session, tenant_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id

    # ── reads ────────────────────────────────────────────────────────────────
    def get(self, task_id: int) -> Task | None:
        task = self.session.get(Task, task_id)
        # Tenant isolation: a row from another tenant is invisible.
        return task if task is not None and task.tenant_id == self.tenant_id else None

    def list(self) -> list[Task]:
        """This tenant's tasks, newest first."""
        stmt = (
            select(Task)
            .where(Task.tenant_id == self.tenant_id)
            .order_by(Task.created_at.desc(), Task.id.desc())
        )
        return list(self.session.scalars(stmt))

    def has_open(self, lead_cluster_id: str, source: str) -> bool:
        """True if this lead has at least one non-done task from ``source``.

        A status-filtered EXISTS/COUNT (PERF-023) — the auto-follow-up rule's
        'is there already an open chase?' test, instead of hydrating every auto
        task for the lead and filtering in Python."""
        stmt = (
            select(func.count())
            .select_from(Task)
            .where(
                Task.tenant_id == self.tenant_id,
                Task.lead_cluster_id == lead_cluster_id,
                Task.source == source,
                Task.status != DONE_STATUS,
            )
            .limit(1)
        )
        return bool(self.session.scalar(stmt))

    def cancel_open(self, lead_cluster_id: str, source: str) -> int:
        """Delete this lead's non-done tasks from ``source``; return how many.

        One tenant+lead+source+status DELETE (PERF-023) — the cancel-on-reply
        path, instead of loading then deleting row-by-row."""
        result = self.session.execute(
            delete(Task).where(
                Task.tenant_id == self.tenant_id,
                Task.lead_cluster_id == lead_cluster_id,
                Task.source == source,
                Task.status != DONE_STATUS,
            )
        )
        self.session.commit()
        # A DELETE returns a CursorResult at runtime; SQLAlchemy types execute()
        # as the base Result, which has no .rowcount.
        return int(cast(CursorResult, result).rowcount or 0)

    # ── writes ───────────────────────────────────────────────────────────────
    def create(
        self,
        *,
        title: str,
        description: str = "",
        created_by_user_id: int | None = None,
        status: str = INITIAL_TASK_STATUS,
        priority: str = "none",
        due_date: date | None = None,
        assignee_user_id: int | None = None,
        lead_cluster_id: str | None = None,
        tower_asr: str | None = None,
        labels: str | list[str] | None = None,
        source: str = "manual",
    ) -> Task:
        if status not in TASK_STATUSES:
            raise InvalidTaskStatus(f"unknown task status {status!r}")
        if priority not in TASK_PRIORITIES:
            raise InvalidTaskPriority(f"unknown task priority {priority!r}")
        task = Task(
            tenant_id=self.tenant_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            due_date=due_date,
            assignee_user_id=assignee_user_id,
            lead_cluster_id=lead_cluster_id or None,
            tower_asr=tower_asr or None,
            labels=normalize_labels(labels),
            source=source,
            created_by_user_id=created_by_user_id,
            completed_at=_utcnow() if status == DONE_STATUS else None,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def update(
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        # Module-level _UNSET sentinel: "leave unchanged" (default) vs. passing
        # None ("clear to null"). The _Sentinel union lets pyright narrow each
        # to its real type after the `is not _UNSET` guard below.
        due_date: date | None | _Sentinel = _UNSET,
        assignee_user_id: int | None | _Sentinel = _UNSET,
        lead_cluster_id: str | None | _Sentinel = _UNSET,
        tower_asr: str | None | _Sentinel = _UNSET,
        labels: str | list[str] | None = None,
    ) -> Task | None:
        """Patch a task (tenant-scoped). Setting status to ``done`` stamps
        ``completed_at``; moving it back off ``done`` clears it. The nullable
        link/assignee/due fields use a sentinel so passing ``None`` *clears*
        them while omitting leaves them unchanged. Returns the updated task,
        or None if it doesn't belong to this tenant."""
        task = self.get(task_id)
        if task is None:
            return None
        if status is not None:
            if status not in TASK_STATUSES:
                raise InvalidTaskStatus(f"unknown task status {status!r}")
            if status == DONE_STATUS and task.status != DONE_STATUS:
                task.completed_at = _utcnow()
            elif status != DONE_STATUS and task.status == DONE_STATUS:
                task.completed_at = None
            task.status = status
        if priority is not None:
            if priority not in TASK_PRIORITIES:
                raise InvalidTaskPriority(f"unknown task priority {priority!r}")
            task.priority = priority
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if labels is not None:
            task.labels = normalize_labels(labels)
        if due_date is not _UNSET:
            task.due_date = due_date
        if assignee_user_id is not _UNSET:
            task.assignee_user_id = assignee_user_id
        if lead_cluster_id is not _UNSET:
            task.lead_cluster_id = lead_cluster_id or None
        if tower_asr is not _UNSET:
            task.tower_asr = tower_asr or None
        self.session.commit()
        self.session.refresh(task)
        return task

    def list_filtered(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        assignee_user_id: int | None = None,
        unassigned: bool = False,
        lead_cluster_id: str | None = None,
        tower_asr: str | None = None,
        source: str | None = None,
        label: str | None = None,
        due_before: date | None = None,
        q: str | None = None,
    ) -> list[Task]:
        """Tenant's tasks narrowed by any subset of fields (#110). Mirrors the
        client task-filter registry's semantics. Free-text ``q`` matches
        title/description (case-insensitive contains)."""
        stmt = select(Task).where(Task.tenant_id == self.tenant_id)
        if status:
            stmt = stmt.where(Task.status == status)
        if priority:
            stmt = stmt.where(Task.priority == priority)
        if unassigned:
            stmt = stmt.where(Task.assignee_user_id.is_(None))
        elif assignee_user_id is not None:
            stmt = stmt.where(Task.assignee_user_id == assignee_user_id)
        if lead_cluster_id:
            stmt = stmt.where(Task.lead_cluster_id == lead_cluster_id)
        if tower_asr:
            stmt = stmt.where(Task.tower_asr == tower_asr)
        if source:
            stmt = stmt.where(Task.source == source)
        if label:
            # comma-separated store → substring match on the normalized label.
            stmt = stmt.where(Task.labels.ilike(f"%{normalize_labels(label)}%"))
        if due_before is not None:
            stmt = stmt.where(Task.due_date.is_not(None), Task.due_date <= due_before)
        if q and q.strip():
            like = f"%{q.strip().lower()}%"
            # SQLite LIKE is case-insensitive for ASCII; lower() both sides for
            # parity with Postgres ILIKE.
            from sqlalchemy import func

            stmt = stmt.where(
                or_(
                    func.lower(Task.title).like(like),
                    func.lower(Task.description).like(like),
                )
            )
        stmt = stmt.order_by(Task.created_at.desc(), Task.id.desc())
        return list(self.session.scalars(stmt))

    def delete(self, task_id: int) -> bool:
        """Delete a task (tenant-scoped). Returns True if a row was removed."""
        task = self.get(task_id)
        if task is None:
            return False
        self.session.delete(task)
        self.session.commit()
        return True
