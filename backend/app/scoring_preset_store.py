"""Tenant-shared scoring presets (UI overhaul P4 / #115, ADR-058 amended).

Tenant-scoped CRUD for named scoring configs — the whole team shares them.
``config`` is an opaque JSON string the client owns; this layer never inspects
it. At most one default per tenant (set_default clears the others).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ScoringPreset


class ScoringPresetStore:
    def __init__(self, session: Session, tenant_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def list(self) -> list[ScoringPreset]:
        stmt = (
            select(ScoringPreset)
            .where(ScoringPreset.tenant_id == self.tenant_id)
            .order_by(ScoringPreset.name)
        )
        return list(self.session.scalars(stmt))

    def get(self, preset_id: int) -> ScoringPreset | None:
        p = self.session.get(ScoringPreset, preset_id)
        return p if p is not None and p.tenant_id == self.tenant_id else None

    def create(self, *, name: str, config: str, is_default: bool = False) -> ScoringPreset:
        preset = ScoringPreset(
            tenant_id=self.tenant_id, name=name, config=config, is_default=is_default
        )
        self.session.add(preset)
        self.session.flush()
        if is_default:
            self._clear_other_defaults(preset.id)
        self.session.commit()
        self.session.refresh(preset)
        return preset

    def set_default(self, preset_id: int) -> ScoringPreset | None:
        preset = self.get(preset_id)
        if preset is None:
            return None
        self._clear_other_defaults(preset.id)
        preset.is_default = True
        self.session.commit()
        self.session.refresh(preset)
        return preset

    def delete(self, preset_id: int) -> bool:
        preset = self.get(preset_id)
        if preset is None:
            return False
        self.session.delete(preset)
        self.session.commit()
        return True

    def _clear_other_defaults(self, keep_id: int) -> None:
        for p in self.list():
            if p.id != keep_id and p.is_default:
                p.is_default = False
