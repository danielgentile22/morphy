"""Tenant-shared scoring presets (UI overhaul P4 / #115, ADR-058 amended).

Tenant-scoped CRUD for named scoring configs — the whole team shares them.
``config`` is an opaque JSON string the client owns; this layer never inspects
it. At most one default per tenant (set_default clears the others).
"""

from __future__ import annotations

from sqlalchemy import select, update

from .models import ScoringPreset
from .tenant_scoped_store import TenantScopedStore


class ScoringPresetStore(TenantScopedStore):
    def list(self) -> list[ScoringPreset]:
        stmt = self.scoped(select(ScoringPreset)).order_by(ScoringPreset.name)
        return list(self.session.scalars(stmt))

    def get(self, preset_id: int) -> ScoringPreset | None:
        return self.get_scoped(ScoringPreset, preset_id)

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
        # One targeted UPDATE instead of SELECT-all + per-row ORM mutation
        # (PERF-034). ``synchronize_session="evaluate"`` flips the flag on any
        # already-loaded preset in this session too, so the identity map stays
        # consistent without an extra fetch.
        self.session.execute(
            self.scoped(
                update(ScoringPreset).where(
                    ScoringPreset.id != keep_id,
                    ScoringPreset.is_default.is_(True),
                )
            )
            .values(is_default=False)
            .execution_options(synchronize_session="evaluate"),
        )
