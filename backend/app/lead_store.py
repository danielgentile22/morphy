"""Tenant-scoped persistence for Lead state.

Every method filters by ``self.tenant_id`` — the single chokepoint that
enforces multi-tenant isolation (ADR-055). A legal status change
auto-logs a ``contact_attempt`` row (``channel='status'``) so a Lead's
history is complete without extra typing.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .lead_status import INITIAL_STATUS, validate_transition
from .models import ContactAttempt, Lead


class LeadStore:
    def __init__(self, session: Session, tenant_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id

    # ── reads ──────────────────────────────────────────────────────────────
    def get_lead(self, display_cluster_id: str) -> Lead | None:
        return self.session.get(Lead, (self.tenant_id, display_cluster_id))

    def list_leads(self, statuses: set[str] | None = None) -> list[Lead]:
        stmt = select(Lead).where(Lead.tenant_id == self.tenant_id)
        if statuses is not None:
            stmt = stmt.where(Lead.status.in_(statuses))
        return list(self.session.scalars(stmt))

    def status_map(self) -> dict[str, str]:
        """``display_cluster_id → status`` for every persisted Lead of this tenant.

        Owners absent from the map are implicitly at ``INITIAL_STATUS`` —
        the owners index is left-joined against this.
        """
        return {lead.display_cluster_id: lead.status for lead in self.list_leads()}

    def list_attempts(self, display_cluster_id: str) -> list[ContactAttempt]:
        stmt = (
            select(ContactAttempt)
            .where(
                ContactAttempt.tenant_id == self.tenant_id,
                ContactAttempt.display_cluster_id == display_cluster_id,
            )
            .order_by(ContactAttempt.occurred_on.desc(), ContactAttempt.id.desc())
        )
        return list(self.session.scalars(stmt))

    # ── writes ─────────────────────────────────────────────────────────────
    def get_or_create(self, display_cluster_id: str) -> Lead:
        lead = self.get_lead(display_cluster_id)
        if lead is None:
            lead = Lead(
                tenant_id=self.tenant_id,
                display_cluster_id=display_cluster_id,
                status=INITIAL_STATUS,
                notes="",
            )
            self.session.add(lead)
            self.session.flush()
        return lead

    def upsert(
        self,
        display_cluster_id: str,
        *,
        status: str | None = None,
        notes: str | None = None,
    ) -> Lead:
        """Set status and/or notes for a Lead, creating it at New if needed.

        A status change is validated against the ladder
        (``InvalidTransition`` on an illegal move) and auto-logs an
        activity row. Persists in one transaction.
        """
        lead = self.get_or_create(display_cluster_id)
        if status is not None and status != lead.status:
            validate_transition(lead.status, status)
            self._log_status_change(display_cluster_id, lead.status, status)
            lead.status = status
        if notes is not None:
            lead.notes = notes
        self.session.commit()
        self.session.refresh(lead)
        return lead

    def append_attempt(
        self,
        display_cluster_id: str,
        *,
        channel: str,
        outcome: str = "",
        note: str = "",
        occurred_on: date | None = None,
    ) -> ContactAttempt:
        attempt = ContactAttempt(
            tenant_id=self.tenant_id,
            display_cluster_id=display_cluster_id,
            occurred_on=occurred_on or date.today(),
            channel=channel,
            outcome=outcome,
            note=note,
        )
        self.session.add(attempt)
        self.session.commit()
        self.session.refresh(attempt)
        return attempt

    def _log_status_change(self, display_cluster_id: str, frm: str, to: str) -> None:
        self.session.add(
            ContactAttempt(
                tenant_id=self.tenant_id,
                display_cluster_id=display_cluster_id,
                occurred_on=date.today(),
                channel="status",
                outcome=f"{frm}→{to}",
                note="",
            )
        )
