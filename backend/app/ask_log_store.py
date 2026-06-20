"""Tenant-scoped persistence for "Ask Claude" Q&A (PRD #187 / slice 3 / #190).

Mirrors ``TaskStore``: a thin store whose every read and write is filtered by
``self.tenant_id`` — the multi-tenant isolation chokepoint. ``record(...)``
writes one completed question+answer with its context snapshot; ``list`` /
``get`` read it back (used by tests now, and the future "promote answers into
the catalog" review later — no read *endpoint* ships in this slice).
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AskLog


def join_signal_ids(ids: Iterable[str] | None) -> str:
    """The on-screen signal ids as a stable comma-separated string (order
    preserved, blanks dropped). '' when none — the storage form of the
    context snapshot's signal list."""
    if ids is None:
        return ""
    return ",".join(s for s in (str(x).strip() for x in ids) if s)


def split_signal_ids(stored: str) -> list[str]:
    """Inverse of :func:`join_signal_ids` — the stored string back to a list."""
    return [s for s in stored.split(",") if s]


class AskLogStore:
    def __init__(self, session: Session, tenant_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id

    # ── writes ───────────────────────────────────────────────────────────────
    def record(
        self,
        *,
        username: str,
        question: str,
        answer: str,
        route: str = "",
        selection: str | None = None,
        signal_ids: Iterable[str] | None = None,
        model: str = "",
        user_id: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> AskLog:
        """Persist one completed Q&A with its context snapshot for this tenant.

        Called after a stream finishes cleanly; the caller treats any failure
        here as best-effort (the answer is already shown), so this never has to
        guard the stream itself."""
        row = AskLog(
            tenant_id=self.tenant_id,
            username=username,
            user_id=user_id,
            question=question,
            answer=answer,
            route=route,
            selection=selection,
            signal_ids=join_signal_ids(signal_ids),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    # ── reads (no endpoint yet — tests + the future review path) ─────────────
    def get(self, ask_id: int) -> AskLog | None:
        row = self.session.get(AskLog, ask_id)
        # Tenant isolation: a row from another tenant is invisible.
        return row if row is not None and row.tenant_id == self.tenant_id else None

    def list(self) -> list[AskLog]:
        """This tenant's stored Q&A, newest first."""
        stmt = (
            select(AskLog)
            .where(AskLog.tenant_id == self.tenant_id)
            .order_by(AskLog.created_at.desc(), AskLog.id.desc())
        )
        return list(self.session.scalars(stmt))
