"""Per-tenant settings (UI overhaul P5 / #116).

A thin typed accessor over the generic ``tenant_setting`` key/value table, with
defaults baked in so a tenant that never touched settings still reads sane
values. Today: the auto-follow-up rule's on/off + window; architected so more
rules slot in as new keys without a schema change.
"""

from __future__ import annotations

from .models import TenantSetting
from .tenant_scoped_store import TenantScopedStore

AUTO_FOLLOWUP_ENABLED = "auto_followup_enabled"
AUTO_FOLLOWUP_WINDOW_DAYS = "auto_followup_window_days"

_DEFAULTS: dict[str, str] = {
    AUTO_FOLLOWUP_ENABLED: "1",  # the rule ships on (the feature is the point)
    AUTO_FOLLOWUP_WINDOW_DAYS: "90",  # ~3 months
}


class SettingsStore(TenantScopedStore):
    def get(self, key: str) -> str:
        row = self.get_scoped(TenantSetting, key)
        return row.value if row is not None else _DEFAULTS.get(key, "")

    def get_bool(self, key: str) -> bool:
        return self.get(key) == "1"

    def get_int(self, key: str, fallback: int = 0) -> int:
        try:
            return int(self.get(key))
        except (ValueError, TypeError):
            return fallback

    def set(self, key: str, value: str) -> None:
        row = self.get_scoped(TenantSetting, key)
        if row is None:
            row = TenantSetting(tenant_id=self.tenant_id, key=key, value=value)
            self.session.add(row)
        else:
            row.value = value
        self.session.commit()

    # ── typed convenience for the auto-follow-up rule ─────────────────────────
    @property
    def auto_followup_enabled(self) -> bool:
        return self.get_bool(AUTO_FOLLOWUP_ENABLED)

    @property
    def auto_followup_window_days(self) -> int:
        return self.get_int(AUTO_FOLLOWUP_WINDOW_DAYS, 90)
