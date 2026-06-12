"""Backend settings — environment-driven; fail-closed enforcement at boot.

A database URL, the path to the static owners index, and the
username/password auth knobs (Slice 1 / #76 — ADR-055). The default
database is a local SQLite file so the backend runs with zero external
services; point ``DATABASE_URL`` at Postgres (``postgresql+psycopg://…``)
in deploy/CI.

Credentials live in the app database (ADR-069, amending ADR-063's storage —
the ``credential`` table is the only credential source; manage it with
``python -m app.users``; a legacy ``users.txt`` imports via the CLI's
``import-file``).

The fail-closed posture is unchanged but enforced at **startup** rather than
import (the table can't be checked before the engine exists, and the
user-management CLI must be importable without a configured secret): with
``AUTH_DEV_MODE`` off (default — the safe state), the app refuses to *serve*
without a real ``AUTH_JWT_SECRET`` and at least one credential row. With it
on, the zero-config loop is preserved: an ephemeral per-process secret and a
built-in ``dev``/``dev`` login seeded **through the same store-writer path**
as the CLI, so dev mode cannot hide credential-resolution bugs.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

# Zero-config dev credential, seeded into the credential table at boot when
# AUTH_DEV_MODE is on and no credential exists — so local runs and CI need no
# setup. Not a secret — it only unlocks the ephemeral, dev-only JWT secret.
DEV_USERNAME = "dev"
DEV_PASSWORD = "dev"
DEV_TEAM = "dev"

# repo root = backend/app/config.py → parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSITE_ROOT = PROJECT_ROOT / "data" / "processed" / "composite"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    owners_index_path: Path
    cors_origins: tuple[str, ...]
    # ── auth (ADR-055) ──────────────────────────────────────────────────────
    jwt_secret: str
    # True when no AUTH_JWT_SECRET was provided and a per-process secret was
    # generated. Outside dev mode this fails the boot check — the app must
    # never serve with a secret that rotates on restart.
    jwt_secret_is_ephemeral: bool
    jwt_algorithm: str
    session_ttl_days: int
    # Master safety switch. False (default) = prod posture: fail closed at
    # boot. True = local dev: ephemeral secret + built-in dev/dev login.
    dev_mode: bool
    # Login brute-force throttle (Slice 2 / #77): after ``login_throttle_max``
    # failed sign-ins for one (ip, username) within
    # ``login_throttle_window_seconds``, further attempts get 429 until the
    # sliding window rolls forward. No hard lockout — the block self-clears, so
    # a known username can't be weaponized to lock a real user out. Per-process
    # state; resets on restart.
    login_throttle_max: int
    login_throttle_window_seconds: float

    @staticmethod
    def from_env() -> Settings:
        default_db = (
            f"sqlite+pysqlite:///{PROJECT_ROOT / 'data' / 'processed' / 'lead_state.sqlite3'}"
        )
        dev_mode = _env_bool("AUTH_DEV_MODE", default=False)
        explicit_secret = os.environ.get("AUTH_JWT_SECRET")

        if dev_mode:
            # Never log the secret value itself — note only whether it's the
            # ephemeral fallback.
            _log.warning(
                "AUTH_DEV_MODE is on: dev auth active (built-in dev/dev login, %s). "
                "Never run this in production.",
                "ephemeral JWT secret" if not explicit_secret else "fixed dev secret",
            )

        return Settings(
            database_url=os.environ.get("DATABASE_URL", default_db),
            owners_index_path=Path(
                os.environ.get("OWNERS_INDEX_PATH", str(COMPOSITE_ROOT / "owners_index.json"))
            ),
            cors_origins=tuple(
                o.strip()
                for o in os.environ.get(
                    "CORS_ORIGINS",
                    "http://localhost:5173,http://localhost:4173",
                ).split(",")
                if o.strip()
            ),
            # Outside dev the boot check refuses to serve on the ephemeral
            # fallback (jwt_secret_is_ephemeral) — building Settings itself
            # must stay side-effect free so tooling (the users CLI) can import
            # config without a secret. Never log it.
            jwt_secret=explicit_secret or secrets.token_urlsafe(32),
            jwt_secret_is_ephemeral=explicit_secret is None,
            jwt_algorithm="HS256",
            session_ttl_days=int(os.environ.get("AUTH_SESSION_TTL_DAYS", "30")),
            dev_mode=dev_mode,
            login_throttle_max=int(os.environ.get("AUTH_LOGIN_THROTTLE_MAX", "5")),
            login_throttle_window_seconds=float(
                os.environ.get("AUTH_LOGIN_THROTTLE_WINDOW_SECONDS", "300")
            ),
        )


settings = Settings.from_env()
