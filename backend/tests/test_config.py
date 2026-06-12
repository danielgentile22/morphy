"""Fail-closed auth posture, keyed on the credential table (ADR-069).

The posture is unchanged from #84/ADR-062 — an instance that can't
authenticate safely must never serve — but enforcement moved from
``Settings.from_env`` (import time) to ``ensure_fail_closed_boot`` (startup):
the credential table can't be checked before the engine exists, and the
user-management CLI must be importable without a configured secret. Outside
dev mode boot requires BOTH a real signing secret and at least one credential
row; in dev mode an empty table seeds the built-in ``dev``/``dev`` login
through the same store-writer path as the CLI. ``users.txt`` is retired —
no env var resurrects it (migration is the CLI's explicit ``import-file``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from backend.app import credentials_store as store
from backend.app.config import PROJECT_ROOT, Settings
from backend.app.credentials_store import ensure_fail_closed_boot
from backend.app.password import hash_password

_SECRET = "a-prod-secret-long-enough-for-hs256-aaaaaaaa"


def _valid_users_file(tmp_path: Path) -> Path:
    f = tmp_path / "users.txt"
    f.write_text(f"alice:{hash_password('wonderland')}:acme\n")
    return f


def _prod_env(monkeypatch, **overrides) -> None:
    """Prod posture: AUTH_DEV_MODE off, all auth env cleared, then overrides."""
    monkeypatch.setenv("AUTH_DEV_MODE", "0")
    for var in ("AUTH_JWT_SECRET", "APP_USERS", "APP_USERS_FILE"):
        monkeypatch.delenv(var, raising=False)
    for var, val in overrides.items():
        monkeypatch.setenv(var, val)


def _dev_env(monkeypatch, **overrides) -> None:
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    for var in ("AUTH_JWT_SECRET", "APP_USERS", "APP_USERS_FILE"):
        monkeypatch.delenv(var, raising=False)
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


def test_prod_boot_refuses_with_no_credential_rows(monkeypatch, engine) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET)
    with pytest.raises(RuntimeError, match="no credentials"):
        ensure_fail_closed_boot(engine, Settings.from_env())


def test_prod_boot_serves_with_a_credential_row(monkeypatch, engine) -> None:
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET)
    with Session(bind=engine, future=True) as s:
        store.add(s, "alice", "acme", "pw")
    ensure_fail_closed_boot(engine, Settings.from_env())  # must not raise


# ── the file path is retired (ADR-069) ───────────────────────────────────────
def test_app_users_file_no_longer_satisfies_the_boot_guard(monkeypatch, engine, tmp_path) -> None:
    # Pre-ADR-069 the boot import would have consumed this file. Now the env
    # var has no effect — migration is the CLI's explicit `import-file`.
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, APP_USERS_FILE=str(_valid_users_file(tmp_path)))
    with pytest.raises(RuntimeError, match="no credentials"):
        ensure_fail_closed_boot(engine, Settings.from_env())
    with Session(bind=engine, future=True) as s:
        assert store.count(s) == 0  # nothing was silently imported


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


# ── dev mode ─────────────────────────────────────────────────────────────────
def test_dev_mode_seeds_dev_dev_through_the_store(monkeypatch, engine) -> None:
    _dev_env(monkeypatch)
    cfg = Settings.from_env()  # no secret, no credentials — fine in dev
    assert cfg.dev_mode is True
    assert cfg.jwt_secret  # ephemeral secret generated
    ensure_fail_closed_boot(engine, cfg)
    with Session(bind=engine, future=True) as s:
        # Seeded through the same writer path as the CLI (ADR-069) — the same
        # three-way authenticate must accept it.
        assert store.authenticate(s, "dev", "dev").ok


def test_dev_mode_defers_to_existing_credentials(monkeypatch, engine) -> None:
    _dev_env(monkeypatch)
    with Session(bind=engine, future=True) as s:
        store.add(s, "alice", "acme", "pw")
    ensure_fail_closed_boot(engine, Settings.from_env())
    with Session(bind=engine, future=True) as s:
        assert store.get(s, "dev") is None  # no seed over real credentials


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


# ── volume-pinned overrides (prod hosting / #96, ADR-064) ────────────────────
def test_prod_honors_the_volume_database_url(monkeypatch) -> None:
    # The deploy pins DATABASE_URL at the Fly volume. If from_env didn't honor
    # the override, writes would land on the ephemeral in-container path — lost
    # on every redeploy and never seen by Litestream (PRD #96 pinned gotcha #1).
    volume_db = "sqlite+pysqlite:////data/lead_state.sqlite3"
    _prod_env(monkeypatch, AUTH_JWT_SECRET=_SECRET, DATABASE_URL=volume_db)
    assert Settings.from_env().database_url == volume_db


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
