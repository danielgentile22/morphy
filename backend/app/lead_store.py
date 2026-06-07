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

    def tenant_attempts(self) -> list[ContactAttempt]:
        """Every activity row for this tenant, newest first — the read model
        the Dashboard derivations (Attention #111, Calendar/History #112,
        Stats #113) assemble over."""
        stmt = (
            select(ContactAttempt)
            .where(ContactAttempt.tenant_id == self.tenant_id)
            .order_by(ContactAttempt.occurred_on.desc(), ContactAttempt.id.desc())
        )
        return list(self.session.scalars(stmt))

    def latest_flags(self) -> dict[str, str]:
        """``display_cluster_id → triggering ASR`` for every Lead with a
        ``channel='flag'`` activity row — the antenna that sparked pursuit
        (#109, ADR-067/D2). Latest flag per owner wins. One query for the
        whole worklist (no N+1)."""
        stmt = (
            select(ContactAttempt)
            .where(
                ContactAttempt.tenant_id == self.tenant_id,
                ContactAttempt.channel == "flag",
            )
            .order_by(ContactAttempt.occurred_on.asc(), ContactAttempt.id.asc())
        )
        # Iterate oldest→newest so the last write per cid is the latest flag.
        out: dict[str, str] = {}
        for a in self.session.scalars(stmt):
            if a.outcome:
                out[a.display_cluster_id] = a.outcome
        return out

    def list_replies(self, display_cluster_id: str) -> list[ContactAttempt]:
        """Inbound activity (replies) for a Lead — the events the Dashboard
        attention feed + auto follow-up rule key on (#106, ADR-066)."""
        stmt = (
            select(ContactAttempt)
            .where(
                ContactAttempt.tenant_id == self.tenant_id,
                ContactAttempt.display_cluster_id == display_cluster_id,
                ContactAttempt.direction == "inbound",
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

    # Editable contact fields (Slice 3 / #49) — applied verbatim when present.
    CONTACT_FIELDS = ("contact_name", "contact_phone", "contact_email", "best_channel")

    def upsert(
        self,
        display_cluster_id: str,
        *,
        status: str | None = None,
        notes: str | None = None,
        contact: dict[str, str] | None = None,
        logged_by_user_id: int | None = None,
    ) -> Lead:
        """Set status, notes, and/or contact fields for a Lead, creating it
        at New if needed.

        A status change is validated against the ladder
        (``InvalidTransition`` on an illegal move) and auto-logs an
        activity row. ``contact`` is a partial dict over ``CONTACT_FIELDS``;
        unknown keys are ignored. Persists in one transaction.
        """
        lead = self.get_or_create(display_cluster_id)
        if status is not None and status != lead.status:
            validate_transition(lead.status, status)
            self._log_status_change(display_cluster_id, lead.status, status, logged_by_user_id)
            lead.status = status
        if notes is not None:
            lead.notes = notes
        if contact:
            for field in self.CONTACT_FIELDS:
                if field in contact and contact[field] is not None:
                    setattr(lead, field, contact[field])
        self.session.commit()
        self.session.refresh(lead)
        return lead

    def pursue(
        self,
        display_cluster_id: str,
        *,
        trigger_asr: str = "",
        logged_by_user_id: int | None = None,
    ) -> Lead:
        """Pursue an owner from Explore (#109, ADR-067/D2): advance New →
        Researching (auto-logging the status row) and record the triggering
        antenna as a ``channel='flag'`` activity row — so "why are we calling
        them?" survives without a schema change. An owner already off New is
        left at its status; an additional trigger may still be flagged.
        Idempotent on the status side (re-pursuing never illegally advances)."""
        lead = self.get_or_create(display_cluster_id)
        if lead.status == INITIAL_STATUS:
            self._log_status_change(
                display_cluster_id, lead.status, "researching", logged_by_user_id
            )
            lead.status = "researching"
        if trigger_asr:
            self.session.add(
                ContactAttempt(
                    tenant_id=self.tenant_id,
                    display_cluster_id=display_cluster_id,
                    occurred_on=date.today(),
                    channel="flag",
                    outcome=trigger_asr,
                    logged_by_user_id=logged_by_user_id,
                )
            )
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
        direction: str = "outbound",
        logged_by_user_id: int | None = None,
    ) -> ContactAttempt:
        """Append an activity event. ``direction='inbound'`` records a *reply*
        (#106); the default ``'outbound'`` is a touch we made. ``logged_by_user_id``
        attributes it to a teammate (#112). Creates the Lead at New if absent
        (logging a reply must never advance status — a reply can arrive with no
        status change)."""
        self.get_or_create(display_cluster_id)
        attempt = ContactAttempt(
            tenant_id=self.tenant_id,
            display_cluster_id=display_cluster_id,
            occurred_on=occurred_on or date.today(),
            channel=channel,
            outcome=outcome,
            note=note,
            direction=direction,
            logged_by_user_id=logged_by_user_id,
        )
        self.session.add(attempt)
        self.session.commit()
        self.session.refresh(attempt)
        return attempt

    def _log_status_change(
        self, display_cluster_id: str, frm: str, to: str, logged_by_user_id: int | None = None
    ) -> None:
        self.session.add(
            ContactAttempt(
                tenant_id=self.tenant_id,
                display_cluster_id=display_cluster_id,
                occurred_on=date.today(),
                channel="status",
                outcome=f"{frm}→{to}",
                note="",
                logged_by_user_id=logged_by_user_id,
            )
        )
