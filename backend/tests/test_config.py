"""Fail-closed auth posture (Slice 2 hardening / #48).

With ``AUTH_DEV_MODE`` off (the default, prod) the app refuses to build a
config that can't authenticate safely — no signing secret, no sign-in gate
— and the dev-only token echo is forced off regardless of env. With it on,
the zero-config local loop is preserved.
"""

from __future__ import annotations

import pytest

from backend.app.config import Settings

_SECRET = "a-prod-secret-long-enough-for-hs256-aaaaaaaa"


def _prod_env(monkeypatch, **overrides) -> None:
    """Prod posture: AUTH_DEV_MODE off, all auth env cleared, then overrides."""
    monkeypatch.setenv("AUTH_DEV_MODE", "0")
    for var in (
        "AUTH_JWT_SECRET",
        "AUTH_ALLOWED_EMAILS",
        "AUTH_ALLOW_OPEN_SIGNUP",
        "AUTH_EXPOSE_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    for var, val in overrides.items():
        monkeypatch.setenv(var, val)


def test_prod_requires_jwt_secret(monkeypatch) -> None:
    _prod_env(monkeypatch, AUTH_ALLOWED_EMAILS="a@b.com")
    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
        Settings.from_env()


def test_prod_requires_a_signin_gate(monkeypatch) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET)
    with pytest.raises(RuntimeError, match="AUTH_ALLOWED_EMAILS"):
        Settings.from_env()


def test_prod_open_signup_is_an_explicit_opt_in(monkeypatch) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, AUTH_ALLOW_OPEN_SIGNUP="1")
    s = Settings.from_env()  # no allowlist, but open sign-up was chosen → OK
    assert s.dev_mode is False
    assert s.allow_open_signup is True


def test_prod_forces_token_echo_off(monkeypatch) -> None:
    # Even asked on, the raw-token echo is never honored outside dev.
    _prod_env(
        monkeypatch,
        AUTH_JWT_SECRET=_SECRET,
        AUTH_ALLOWED_EMAILS="a@b.com",
        AUTH_EXPOSE_TOKEN="1",
    )
    assert Settings.from_env().expose_token_in_response is False


def test_prod_uses_the_provided_secret(monkeypatch) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, AUTH_ALLOWED_EMAILS="a@b.com")
    assert Settings.from_env().jwt_secret == _SECRET


def test_dev_mode_is_zero_config(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    for var in ("AUTH_JWT_SECRET", "AUTH_ALLOWED_EMAILS"):
        monkeypatch.delenv(var, raising=False)
    s = Settings.from_env()  # no secret, no allowlist — fine in dev
    assert s.dev_mode is True
    assert s.jwt_secret  # ephemeral secret generated
    assert s.expose_token_in_response is True


def test_session_ttl_default_is_thirty_days(monkeypatch) -> None:
    # Bumped from 2 → 30 with the username/password front door (Slice 1 / #76):
    # a daily-use tool shouldn't force re-auth constantly.
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    monkeypatch.delenv("AUTH_SESSION_TTL_DAYS", raising=False)
    assert Settings.from_env().session_ttl_days == 30
