"""Fail-closed auth posture, keyed on the credential table (PRD #130).

The posture is unchanged from #84/ADR-062 — an instance that can't
authenticate safely must never serve — but enforcement moved from
``Settings.from_env`` (import time) to ``ensure_fail_closed_boot`` (startup):
the credential table can't be checked before the engine exists, and the
user-management CLI must be importable without a configured secret. Outside
dev mode boot requires BOTH a real signing secret and at least one credential
row; an empty table one-shot-imports the legacy users.txt (the PRD's storage
cutover) or, in dev mode, seeds the built-in ``dev``/``dev`` login through
the same store-writer path as the CLI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from backend.app import credentials_store as store
from backend.app.config import DEFAULT_CREDENTIALS_PATH, PROJECT_ROOT, Settings
from backend.app.credentials_store import ensure_fail_closed_boot
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
    # Point the *legacy-import* path away from any real backend/users.txt on
    # the developer's machine, so these tests are hermetic.
    monkeypatch.setenv("APP_USERS_FILE", "/nonexistent/users.txt")
    for var, val in overrides.items():
        monkeypatch.setenv(var, val)


def _dev_env(monkeypatch, **overrides) -> None:
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    for var in ("AUTH_JWT_SECRET", "APP_USERS", "APP_USERS_FILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("APP_USERS_FILE", "/nonexistent/users.txt")
    for var, val in overrides.items():
        monkeypatch.setenv(var, val)


# ── fail-closed boot (prod) ──────────────────────────────────────────────────
def test_prod_boot_requires_a_real_jwt_secret(monkeypatch, engine) -> None:
    _prod_env(monkeypatch)
    cfg = Settings.from_env()
    assert cfg.jwt_secret_is_ephemeral  # from_env itself never raises (CLI import)
    with Session(bind=engine, future=True) as s:
        store.add(s, "alice", "acme", "pw")  # credentials fine — only the secret is missing
    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
        ensure_fail_closed_boot(engine, cfg)


def test_prod_boot_refuses_with_no_credentials_anywhere(monkeypatch, engine) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET)
    with pytest.raises(RuntimeError, match="no credentials"):
        ensure_fail_closed_boot(engine, Settings.from_env())


def test_prod_boot_refuses_on_a_file_with_no_valid_entry(monkeypatch, engine, tmp_path) -> None:
    # Comments + a team-less (legacy-shaped) line: parseable, but no credential
    # to import — still fail closed.
    f = _users_file(tmp_path, "# just a comment", f"alice:{hash_password('pw')}")
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, APP_USERS_FILE=str(f))
    with pytest.raises(RuntimeError, match="no credentials"):
        ensure_fail_closed_boot(engine, Settings.from_env())


def test_prod_boot_serves_with_a_credential_row(monkeypatch, engine) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET)
    with Session(bind=engine, future=True) as s:
        store.add(s, "alice", "acme", "pw")
    ensure_fail_closed_boot(engine, Settings.from_env())  # must not raise


# ── the one-shot cutover import (PRD #130) ────────────────────────────────────
def test_an_empty_table_imports_the_legacy_file_once(monkeypatch, engine, tmp_path) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, APP_USERS_FILE=str(_valid_users_file(tmp_path)))
    cfg = Settings.from_env()
    ensure_fail_closed_boot(engine, cfg)
    with Session(bind=engine, future=True) as s:
        assert store.authenticate(s, "alice", "wonderland").ok
        assert store.count(s) == 1
    # A second boot sees rows and must not re-import (no duplicates, no error).
    ensure_fail_closed_boot(engine, cfg)
    with Session(bind=engine, future=True) as s:
        assert store.count(s) == 1


def test_a_populated_table_outranks_the_file(monkeypatch, engine, tmp_path) -> None:
    # Once credentials live in the DB, the file is never consulted again —
    # even if it still exists with different users.
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, APP_USERS_FILE=str(_valid_users_file(tmp_path)))
    with Session(bind=engine, future=True) as s:
        store.add(s, "carol", "globex", "pw-c")
    ensure_fail_closed_boot(engine, Settings.from_env())
    with Session(bind=engine, future=True) as s:
        assert store.get(s, "alice") is None  # the file's user was not imported
        assert store.authenticate(s, "carol", "pw-c").ok


# ── dev mode ─────────────────────────────────────────────────────────────────
def test_dev_mode_seeds_dev_dev_through_the_store(monkeypatch, engine) -> None:
    _dev_env(monkeypatch)
    cfg = Settings.from_env()  # no secret, no credentials — fine in dev
    assert cfg.dev_mode is True
    assert cfg.jwt_secret  # ephemeral secret generated
    ensure_fail_closed_boot(engine, cfg)
    with Session(bind=engine, future=True) as s:
        # Seeded through the same writer path as the CLI (user story 13) —
        # the same three-way authenticate must accept it.
        assert store.authenticate(s, "dev", "dev").ok


def test_dev_mode_prefers_an_existing_valid_file(monkeypatch, engine, tmp_path) -> None:
    _dev_env(monkeypatch, APP_USERS_FILE=str(_valid_users_file(tmp_path)))
    ensure_fail_closed_boot(engine, Settings.from_env())
    with Session(bind=engine, future=True) as s:
        assert store.authenticate(s, "alice", "wonderland").ok  # imported
        assert store.get(s, "dev") is None  # the built-in seed deferred to it


# ── from_env stays side-effect free (the CLI imports config) ─────────────────
def test_from_env_never_raises_without_a_secret(monkeypatch) -> None:
    _prod_env(monkeypatch)
    s = Settings.from_env()
    assert s.jwt_secret_is_ephemeral is True
    assert s.jwt_secret  # generated — but boot refuses to serve on it


def test_from_env_carries_an_explicit_secret(monkeypatch) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET)
    s = Settings.from_env()
    assert s.jwt_secret == _SECRET
    assert s.jwt_secret_is_ephemeral is False


def test_the_app_users_env_var_has_no_effect(monkeypatch, engine) -> None:
    # The pre-#84 credential source. Setting it must not satisfy the boot
    # guard — the env-var path is gone entirely.
    _prod_env(
        monkeypatch,
        AUTH_JWT_SECRET=_SECRET,
        APP_USERS=f"alice:{hash_password('wonderland')}",
    )
    with pytest.raises(RuntimeError, match="no credentials"):
        ensure_fail_closed_boot(engine, Settings.from_env())


# ── volume-pinned overrides (prod hosting / #96, ADR-064) ────────────────────
def test_prod_honors_the_volume_database_url(monkeypatch) -> None:
    # The deploy pins DATABASE_URL at the Fly volume. If from_env didn't honor
    # the override, writes would land on the ephemeral in-container path — lost
    # on every redeploy and never seen by Litestream (PRD #96 pinned gotcha #1).
    volume_db = "sqlite+pysqlite:////data/lead_state.sqlite3"
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, DATABASE_URL=volume_db)
    assert Settings.from_env().database_url == volume_db


def test_prod_honors_the_volume_users_file_for_the_import(monkeypatch, tmp_path) -> None:
    # APP_USERS_FILE=/data/users.txt in prod must win over the repo default, so
    # the one-shot cutover import reads the mounted file ops manage.
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
