"""Fail-closed auth posture (Slice 2 hardening / #48, #77).

With ``AUTH_DEV_MODE`` off (the default, prod) the app refuses to build a
config that can't authenticate safely — it requires **both** a real signing
secret and at least one login credential (``APP_USERS``), so a deploy can be
neither open nor impossible to log into. With it on, the zero-config local loop
is preserved (ephemeral secret + built-in ``dev``/``dev`` login).
"""

from __future__ import annotations

import pytest

from backend.app.config import Settings
from backend.app.password import hash_password

_SECRET = "a-prod-secret-long-enough-for-hs256-aaaaaaaa"
# One real credential for prod-posture tests (the encoded hash never contains
# ',' or ':', so it round-trips through APP_USERS parsing unambiguously).
_CRED = f"alice:{hash_password('wonderland')}"


def _prod_env(monkeypatch, **overrides) -> None:
    """Prod posture: AUTH_DEV_MODE off, all auth env cleared, then overrides."""
    monkeypatch.setenv("AUTH_DEV_MODE", "0")
    for var in ("AUTH_JWT_SECRET", "APP_USERS"):
        monkeypatch.delenv(var, raising=False)
    for var, val in overrides.items():
        monkeypatch.setenv(var, val)


def test_prod_requires_jwt_secret(monkeypatch) -> None:
    _prod_env(monkeypatch, APP_USERS=_CRED)  # credential present, secret missing
    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
        Settings.from_env()


def test_prod_requires_a_credential(monkeypatch) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET)  # secret present, no credential
    with pytest.raises(RuntimeError, match="APP_USERS"):
        Settings.from_env()


def test_prod_boots_with_secret_and_credential(monkeypatch) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, APP_USERS=_CRED)
    s = Settings.from_env()
    assert s.dev_mode is False
    assert "alice" in s.app_users  # parsed + available to the login route


def test_prod_uses_the_provided_secret(monkeypatch) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, APP_USERS=_CRED)
    assert Settings.from_env().jwt_secret == _SECRET


def test_dev_mode_is_zero_config(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    for var in ("AUTH_JWT_SECRET", "APP_USERS"):
        monkeypatch.delenv(var, raising=False)
    s = Settings.from_env()  # no secret, no credential — fine in dev
    assert s.dev_mode is True
    assert s.jwt_secret  # ephemeral secret generated
    assert "dev" in s.app_users  # built-in dev/dev login seeded


def test_session_ttl_default_is_thirty_days(monkeypatch) -> None:
    # Bumped from 2 → 30 with the username/password front door (Slice 1 / #76):
    # a daily-use tool shouldn't force re-auth constantly.
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    monkeypatch.delenv("AUTH_SESSION_TTL_DAYS", raising=False)
    assert Settings.from_env().session_ttl_days == 30


def test_login_throttle_config_defaults(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    for var in ("AUTH_LOGIN_THROTTLE_MAX", "AUTH_LOGIN_THROTTLE_WINDOW_SECONDS"):
        monkeypatch.delenv(var, raising=False)
    s = Settings.from_env()
    assert s.login_throttle_max == 5
    assert s.login_throttle_window_seconds == 300.0
