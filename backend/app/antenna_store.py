"""Tenant-scoped persistence for per-antenna manual state (UI overhaul round 2).

The owners index is read-only; this store is the editable layer over a single
antenna, addressed by ASR. Every method filters by ``self.tenant_id`` — the
same multi-tenant chokepoint as ``LeadStore`` (ADR-055). Rows are created
lazily on first edit, so an antenna with no row is simply unedited.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AntennaOverride


class AntennaStore:
    # The free-text fields a PUT may set (partial). ``archived`` is handled
    # separately because it's a bool, not a string.
    EDITABLE = ("address", "owner_name", "owner_phone", "owner_email", "notes")

    def __init__(self, session: Session, tenant_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id

    # ── reads ──────────────────────────────────────────────────────────────
    def get(self, asr: str) -> AntennaOverride | None:
        return self.session.get(AntennaOverride, (self.tenant_id, asr))

    def archived_asrs(self) -> set[str]:
        """The set of archived ASRs for this tenant — the map + list exclude
        these unless the user opts into showing archived antennas."""
        stmt = select(AntennaOverride.asr).where(
            AntennaOverride.tenant_id == self.tenant_id,
            AntennaOverride.archived.is_(True),
        )
        return set(self.session.scalars(stmt))

    # ── writes ─────────────────────────────────────────────────────────────
    def get_or_create(self, asr: str) -> AntennaOverride:
        row = self.get(asr)
        if row is None:
            row = AntennaOverride(tenant_id=self.tenant_id, asr=asr)
            self.session.add(row)
            self.session.flush()
        return row

    def upsert(
        self,
        asr: str,
        *,
        archived: bool | None = None,
        fields: dict[str, str] | None = None,
    ) -> AntennaOverride:
        """Set the archived flag and/or any subset of the editable text fields
        for an antenna, creating the row at defaults if needed. ``archived=None``
        leaves the flag untouched; ``fields`` is a partial dict over
        ``EDITABLE`` (unknown/None values ignored). Persists in one transaction.
        """
        row = self.get_or_create(asr)
        if archived is not None:
            row.archived = archived
        if fields:
            for field in self.EDITABLE:
                if field in fields and fields[field] is not None:
                    setattr(row, field, fields[field])
        self.session.commit()
        self.session.refresh(row)
        return row
