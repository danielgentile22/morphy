"""Per-user settings (PRD #121) — the first per-user persisted preferences.

A thin typed accessor over the generic ``user_setting`` key/value table, with
defaults baked in so a user who never opened Settings still reads sane values.
Mirrors ``SettingsStore`` exactly, but the row is keyed by ``(tenant_id,
user_id, key)`` instead of ``(tenant_id, key)`` — the preference follows the
*individual*, scoped within their tenant.

``home_view`` and ``filter_default`` are opaque JSON blobs the client owns
(a map "home" position; a saved FilterModel snapshot); this layer persists +
serves them verbatim and never inspects them — the same posture as
``ScoringPreset.config``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import UserSetting
from .tenant_scoped_store import TenantScopedStore

# ── known keys ────────────────────────────────────────────────────────────────
THEME = "theme"  # light | dark | system
COLORBLIND = "colorblind"  # 0 | 1
BASEMAP = "basemap"  # light | voyager | dark | satellite
VIEW_MODE = "view_mode"  # home | last
HOME_VIEW = "home_view"  # JSON {lng,lat,zoom} or ""
FILTER_DEFAULT = "filter_default"  # opaque FilterModel snapshot JSON or ""
FILTER_DEFAULT_APPLY = "filter_default_apply"  # 0 | 1

_DEFAULTS: dict[str, str] = {
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


class UserSettingsStore(TenantScopedStore):
    def __init__(self, session: Session, tenant_id: int, user_id: int) -> None:
        super().__init__(session, tenant_id)
        self.user_id = user_id

    def get(self, key: str) -> str:
        row = self.get_scoped(UserSetting, (self.user_id, key))
        return row.value if row is not None else _DEFAULTS.get(key, "")

    def get_bool(self, key: str) -> bool:
        return self.get(key) == "1"

    def set(self, key: str, value: str) -> None:
        row = self.get_scoped(UserSetting, (self.user_id, key))
        if row is None:
            row = UserSetting(tenant_id=self.tenant_id, user_id=self.user_id, key=key, value=value)
            self.session.add(row)
        else:
            row.value = value
        self.session.commit()

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
