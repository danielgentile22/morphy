"""Fail-closed auth posture, keyed on the credentials file (#84, PRD #83).

With ``AUTH_DEV_MODE`` off (the default, prod) the app refuses to build a
config that can't authenticate safely — it requires **both** a real signing
secret and a credentials file with at least one valid ``username:hash:team``
entry, so a deploy can be neither open nor impossible to log into. With it
on, the zero-config local loop is preserved (ephemeral secret + a built-in
``dev``/``dev`` login seeded through the same file-parsing code path).

The old ``APP_USERS`` env var has **no effect** — the file is the only
credential source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.config import DEFAULT_CREDENTIALS_PATH, PROJECT_ROOT, Settings
from backend.app.password import hash_password

_SECRET = "a-prod-secret-long-enough-for-hs256-aaaaaaaa"


def _users_file(tmp_path: Path, *lines: str) -> Path:
    f = tmp_path / "users.txt"
    f.write_text("\n".join(lines) + "\n" if lines else "")
    return f


def _valid_users_file(tmp_path: Path) -> Path:
    return _users_file(tmp_path, f"alice:{hash_password('wonderland')}:acme")


def _prod_env(monkeypatch, **overrides) -> None:
    """Prod posture: AUTH_DEV_MODE off, all auth env cleared, then overrides."""
    monkeypatch.setenv("AUTH_DEV_MODE", "0")
    for var in ("AUTH_JWT_SECRET", "APP_USERS", "APP_USERS_FILE"):
        monkeypatch.delenv(var, raising=False)
    # Point the *default* credentials path away from any real backend/users.txt
    # on the developer's machine, so these tests are hermetic.
    monkeypatch.setenv("APP_USERS_FILE", "/nonexistent/users.txt")
    for var, val in overrides.items():
        monkeypatch.setenv(var, val)


# ── fail-closed boot (prod) ──────────────────────────────────────────────────
def test_prod_requires_jwt_secret(monkeypatch, tmp_path) -> None:
    _prod_env(monkeypatch, APP_USERS_FILE=str(_valid_users_file(tmp_path)))
    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
        Settings.from_env()


def test_prod_requires_a_credentials_file(monkeypatch) -> None:
    # Secret present, but the credentials file doesn't exist → refuse to boot.
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET)
    with pytest.raises(RuntimeError, match="credentials file"):
        Settings.from_env()


def test_prod_rejects_an_empty_credentials_file(monkeypatch, tmp_path) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, APP_USERS_FILE=str(_users_file(tmp_path)))
    with pytest.raises(RuntimeError, match="credentials file"):
        Settings.from_env()


def test_prod_rejects_a_file_with_no_valid_entry(monkeypatch, tmp_path) -> None:
    # Comments + a team-less (legacy-shaped) line: parseable, but no credential.
    f = _users_file(tmp_path, "# just a comment", f"alice:{hash_password('pw')}")
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, APP_USERS_FILE=str(f))
    with pytest.raises(RuntimeError, match="credentials file"):
        Settings.from_env()


def test_prod_boots_with_secret_and_valid_file(monkeypatch, tmp_path) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, APP_USERS_FILE=str(_valid_users_file(tmp_path)))
    s = Settings.from_env()
    assert s.dev_mode is False
    assert s.jwt_secret == _SECRET
    assert s.credentials_path == _valid_users_file(tmp_path)


def test_the_app_users_env_var_has_no_effect(monkeypatch, tmp_path) -> None:
    # The pre-#84 credential source. Setting it must not satisfy the boot
    # guard — the env-var path is gone entirely.
    _prod_env(
        monkeypatch,
        AUTH_JWT_SECRET=_SECRET,
        APP_USERS=f"alice:{hash_password('wonderland')}",
    )
    with pytest.raises(RuntimeError, match="credentials file"):
        Settings.from_env()


# ── volume-pinned overrides (prod hosting / #96, ADR-064) ────────────────────
def test_prod_honors_the_volume_database_url(monkeypatch, tmp_path) -> None:
    # The deploy pins DATABASE_URL at the Fly volume. If from_env didn't honor
    # the override, writes would land on the ephemeral in-container path — lost
    # on every redeploy and never seen by Litestream (PRD #96 pinned gotcha #1).
    volume_db = "sqlite+pysqlite:////data/lead_state.sqlite3"
    _prod_env(
        monkeypatch,
        AUTH_JWT_SECRET=_SECRET,
        APP_USERS_FILE=str(_valid_users_file(tmp_path)),
        DATABASE_URL=volume_db,
    )
    assert Settings.from_env().database_url == volume_db


def test_prod_honors_the_volume_credentials_file_over_the_default(monkeypatch, tmp_path) -> None:
    # APP_USERS_FILE=/data/users.txt in prod must win over the repo default, so
    # auth reads the mounted file Litestream/ops manage (ADR-063).
    users = _valid_users_file(tmp_path)
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, APP_USERS_FILE=str(users))
    s = Settings.from_env()
    assert s.credentials_path == users
    assert s.credentials_path != DEFAULT_CREDENTIALS_PATH


def test_default_database_url_is_the_ephemeral_repo_path_not_the_volume(monkeypatch) -> None:
    # Pins PRD gotcha #1 the other way: with nothing set, the DB defaults UNDER
    # the repo (ephemeral in-container), never the /data volume — so a deploy
    # that forgets the override is data-losing, and this guards the default from
    # silently drifting onto the volume path.
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db = Settings.from_env().database_url
    assert str(PROJECT_ROOT) in db
    assert db != "sqlite+pysqlite:////data/lead_state.sqlite3"


# ── dev mode ─────────────────────────────────────────────────────────────────
def test_dev_mode_is_zero_config_and_goes_through_the_file_path(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    for var in ("AUTH_JWT_SECRET", "APP_USERS", "APP_USERS_FILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("APP_USERS_FILE", "/nonexistent/users.txt")

    s = Settings.from_env()  # no secret, no credentials file — fine in dev
    assert s.dev_mode is True
    assert s.jwt_secret  # ephemeral secret generated
    # The built-in dev login is seeded into a real temp file and parsed through
    # the same code path as production — never an in-memory shortcut.
    from backend.app import credentials

    users = credentials.load(s.credentials_path)
    assert "dev" in users
    assert credentials.authenticate(users, "dev", "dev").ok


def test_dev_mode_prefers_an_existing_valid_file(monkeypatch, tmp_path) -> None:
    f = _valid_users_file(tmp_path)
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    monkeypatch.setenv("APP_USERS_FILE", str(f))
    s = Settings.from_env()
    assert s.credentials_path == f  # the configured file wins over dev seeding


# ── knob defaults (unchanged from the prior slices) ──────────────────────────
def test_session_ttl_default_is_thirty_days(monkeypatch) -> None:
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
