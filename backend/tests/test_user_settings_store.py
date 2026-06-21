"""Per-user settings store (PRD #121) — the first per-user persisted prefs.

Mirrors the ``SettingsStore`` tests but for the ``(tenant_id, user_id, key)``
table: baked-in defaults before any write, set→get round-trip, type coercion,
and — most importantly — that one user's value never leaks to another user or
another tenant.
"""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.user_settings_store import (
    BASEMAP,
    COLORBLIND,
    FILTER_DEFAULT,
    FILTER_DEFAULT_APPLY,
    HOME_VIEW,
    THEME,
    VIEW_MODE,
    UserSettingsStore,
)


def _store(engine: Engine, tenant: int = 1, user: int = 1) -> UserSettingsStore:
    return UserSettingsStore(Session(bind=engine, future=True), tenant, user)


def test_defaults_before_any_write(engine: Engine) -> None:
    s = _store(engine)
    assert s.theme == "system"
    assert s.colorblind is False
    assert s.basemap == "light"
    assert s.view_mode == "last"
    assert s.home_view == ""
    assert s.filter_default == ""
    assert s.filter_default_apply is False


def test_set_get_roundtrip_per_key(engine: Engine) -> None:
    _store(engine).set(THEME, "dark")
    _store(engine).set(COLORBLIND, "1")
    _store(engine).set(BASEMAP, "voyager")
    _store(engine).set(VIEW_MODE, "home")
    _store(engine).set(HOME_VIEW, '{"lng":-92.1,"lat":34.7,"zoom":11.5}')
    _store(engine).set(FILTER_DEFAULT, '{"states":["AR","MT"]}')
    _store(engine).set(FILTER_DEFAULT_APPLY, "1")

    s = _store(engine)
    assert s.theme == "dark"
    assert s.colorblind is True
    assert s.basemap == "voyager"
    assert s.view_mode == "home"
    assert s.home_view == '{"lng":-92.1,"lat":34.7,"zoom":11.5}'
    assert s.filter_default == '{"states":["AR","MT"]}'
    assert s.filter_default_apply is True


def test_opaque_blob_is_persisted_verbatim(engine: Engine) -> None:
    # The backend never inspects filter_default / home_view (same posture as
    # ScoringPreset.config) — a long, nested JSON blob round-trips byte-for-byte.
    blob = '{"states":["AR"],"assessedValue":[1000,50000],"nested":{"a":[1,2,3]}}'
    _store(engine).set(FILTER_DEFAULT, blob)
    assert _store(engine).filter_default == blob


def test_bool_coercion_falls_back_on_garbage(engine: Engine) -> None:
    s = _store(engine)
    s.set(COLORBLIND, "not-a-bool")
    assert _store(engine).get_bool(COLORBLIND) is False  # only "1" is true


def test_settings_are_isolated_per_user_and_per_tenant(engine: Engine) -> None:
    _store(engine, tenant=1, user=1).set(THEME, "dark")

    # Same tenant, different user → still the default.
    assert _store(engine, tenant=1, user=2).theme == "system"
    # Different tenant, same user id → still the default.
    assert _store(engine, tenant=2, user=1).theme == "system"
    # The writer still sees their own value.
    assert _store(engine, tenant=1, user=1).theme == "dark"
