"""Tenant- and per-user key/value settings (UI overhaul P5 / #116; PRD #121).

One KV engine on the ``TenantScopedStore`` base, parameterized by key scope:
``SettingsStore`` reads/writes ``tenant_setting`` rows keyed ``(tenant_id,
key)``; ``UserSettingsStore`` reads/writes ``user_setting`` rows keyed
``(tenant_id, user_id, key)`` — the preference follows the *individual*,
scoped within their tenant. Defaults are baked in so a tenant/user who never
touched settings still reads sane values, and new settings slot in as new
keys without a schema change.

``home_view`` and ``filter_default`` are opaque JSON blobs the client owns
(a map "home" position; a saved FilterModel snapshot); this layer persists +
serves them verbatim and never inspects them — the same posture as
``ScoringPreset.config``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import TenantSetting, UserSetting
from .tenant_scoped_store import TenantScopedStore

# ── tenant-level keys (#116) ──────────────────────────────────────────────────
AUTO_FOLLOWUP_ENABLED = "auto_followup_enabled"
AUTO_FOLLOWUP_WINDOW_DAYS = "auto_followup_window_days"

_TENANT_DEFAULTS: dict[str, str] = {
    AUTO_FOLLOWUP_ENABLED: "1",  # the rule ships on (the feature is the point)
    AUTO_FOLLOWUP_WINDOW_DAYS: "90",  # ~3 months
}

# ── per-user keys (PRD #121) ──────────────────────────────────────────────────
THEME = "theme"  # light | dark | system
COLORBLIND = "colorblind"  # 0 | 1
BASEMAP = "basemap"  # light | voyager | dark | satellite
VIEW_MODE = "view_mode"  # home | last
HOME_VIEW = "home_view"  # JSON {lng,lat,zoom} or ""
FILTER_DEFAULT = "filter_default"  # opaque FilterModel snapshot JSON or ""
FILTER_DEFAULT_APPLY = "filter_default_apply"  # 0 | 1

_USER_DEFAULTS: dict[str, str] = {
    THEME: "system",  # follow the OS by default — no surprise dark/light
    COLORBLIND: "0",
    BASEMAP: "satellite",  # aerial imagery out of the box (frontend falls back
    #                        to Carto Dark when no MapTiler key is built in)
    VIEW_MODE: "last",  # restore where I left off rather than force a home view
    HOME_VIEW: "",
    FILTER_DEFAULT: "",
    FILTER_DEFAULT_APPLY: "0",
}

# The keys the API serves/accepts. Listed explicitly so a typo'd client key is
# ignored rather than silently stored (and so the response shape is stable).
KNOWN_KEYS: tuple[str, ...] = (
    THEME,
    COLORBLIND,
    BASEMAP,
    VIEW_MODE,
    HOME_VIEW,
    FILTER_DEFAULT,
    FILTER_DEFAULT_APPLY,
)


class KeyValueSettings(TenantScopedStore):
    """The shared KV engine: fail-safe reads with baked-in defaults, upsert
    writes. A subclass declares its row model, defaults, and the scope-key
    components between ``tenant_id`` and ``key`` (e.g. ``(user_id,)``)."""

    def __init__(
        self,
        session: Session,
        tenant_id: int,
        *,
        model: type[TenantSetting] | type[UserSetting],
        defaults: dict[str, str],
        scope: tuple[int, ...] = (),
    ) -> None:
        super().__init__(session, tenant_id)
        self._model = model
        self._defaults = defaults
        self._scope = scope

    def get(self, key: str) -> str:
        row = self.get_scoped(self._model, (*self._scope, key))
        return row.value if row is not None else self._defaults.get(key, "")

    def get_bool(self, key: str) -> bool:
        return self.get(key) == "1"

    def get_int(self, key: str, fallback: int = 0) -> int:
        try:
            return int(self.get(key))
        except (ValueError, TypeError):
            return fallback

    def set(self, key: str, value: str) -> None:
        row = self.get_scoped(self._model, (*self._scope, key))
        if row is None:
            self.session.add(self._row(key, value))
        else:
            row.value = value
        self.session.commit()

    def _row(self, key: str, value: str) -> TenantSetting | UserSetting:
        raise NotImplementedError


class SettingsStore(KeyValueSettings):
    """Tenant-level settings — today the auto-follow-up rule's on/off + window."""

    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id, model=TenantSetting, defaults=_TENANT_DEFAULTS)

    def _row(self, key: str, value: str) -> TenantSetting:
        return TenantSetting(tenant_id=self.tenant_id, key=key, value=value)

    # ── typed convenience for the auto-follow-up rule ─────────────────────────
    @property
    def auto_followup_enabled(self) -> bool:
        return self.get_bool(AUTO_FOLLOWUP_ENABLED)

    @property
    def auto_followup_window_days(self) -> int:
        return self.get_int(AUTO_FOLLOWUP_WINDOW_DAYS, 90)


class UserSettingsStore(KeyValueSettings):
    """Per-user settings, scoped by both ``tenant_id`` *and* ``user_id`` —
    no teammate (or other tenant) can see another's preferences."""

    def __init__(self, session: Session, tenant_id: int, user_id: int) -> None:
        super().__init__(
            session,
            tenant_id,
            model=UserSetting,
            defaults=_USER_DEFAULTS,
            scope=(user_id,),
        )
        self.user_id = user_id

    def _row(self, key: str, value: str) -> UserSetting:
        return UserSetting(tenant_id=self.tenant_id, user_id=self.user_id, key=key, value=value)

    # ── typed convenience for each known key ──────────────────────────────────
    @property
    def theme(self) -> str:
        return self.get(THEME)

    @property
    def colorblind(self) -> bool:
        return self.get_bool(COLORBLIND)

    @property
    def basemap(self) -> str:
        return self.get(BASEMAP)

    @property
    def view_mode(self) -> str:
        return self.get(VIEW_MODE)

    @property
    def home_view(self) -> str:
        return self.get(HOME_VIEW)

    @property
    def filter_default(self) -> str:
        return self.get(FILTER_DEFAULT)

    @property
    def filter_default_apply(self) -> bool:
        return self.get_bool(FILTER_DEFAULT_APPLY)

    def resolved(self) -> dict[str, str]:
        """All known keys with defaults filled in — the API response payload."""
        return {key: self.get(key) for key in KNOWN_KEYS}
