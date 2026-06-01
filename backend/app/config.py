"""Backend settings — environment-driven, fail-closed outside dev.

A database URL, the path to the static owners index, and the
username/password auth knobs (Slice 1 / #76 — ADR-055). The default
database is a local SQLite file so the backend runs with zero external
services; point ``DATABASE_URL`` at Postgres (``postgresql+psycopg://…``)
in deploy/CI.

Auth posture is gated on a single switch, ``AUTH_DEV_MODE`` (default
**off** — the safe state). With it off (prod), ``from_env`` refuses to
build without a real ``AUTH_JWT_SECRET`` **and** at least one login
credential (``APP_USERS``) — so a deploy can be neither open nor impossible
to log into. With it on, the zero-config local loop is preserved: an
ephemeral per-process secret and a built-in ``dev``/``dev`` login. The real
secret store lands with #16.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from . import credentials
from .password import hash_password

_log = logging.getLogger(__name__)

# Zero-config dev credential, seeded into the parsed APP_USERS map when
# AUTH_DEV_MODE is on so local runs and CI need no env setup. Not a secret —
# it only unlocks the ephemeral, dev-only JWT secret.
DEV_USERNAME = "dev"
DEV_PASSWORD = "dev"

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
    jwt_algorithm: str
    session_ttl_days: int
    # New users land in this tenant — realizes ADR-055's "reads 1 for now"
    # without a hardcoded tenant on the request path (the tenant now rides
    # on the authenticated JWT). A second tenant is a row add, not a refactor.
    default_tenant_id: int
    # Master safety switch. False (default) = prod posture: fail closed.
    # True = local dev: ephemeral secret + built-in dev/dev login.
    dev_mode: bool
    # Login brute-force throttle (Slice 2 / #77): after ``login_throttle_max``
    # failed sign-ins for one (ip, username) within
    # ``login_throttle_window_seconds``, further attempts get 429 until the
    # sliding window rolls forward. No hard lockout — the block self-clears, so
    # a known username can't be weaponized to lock a real user out. Per-process
    # state; resets on restart.
    login_throttle_max: int
    login_throttle_window_seconds: float
    # Username/password credentials (Slice 1 / #76): {username -> encoded hash},
    # parsed from APP_USERS at load. The username/password login route checks
    # against this; in dev a built-in ``dev``/``dev`` entry is seeded.
    app_users: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def from_env() -> Settings:
        default_db = (
            f"sqlite+pysqlite:///{PROJECT_ROOT / 'data' / 'processed' / 'lead_state.sqlite3'}"
        )
        dev_mode = _env_bool("AUTH_DEV_MODE", default=False)
        explicit_secret = os.environ.get("AUTH_JWT_SECRET")
        # The login credential set (Slice 1 / #76). The fail-closed guard below
        # is expressed in terms of *this* — an instance with no credential is
        # un-loginnable and must not boot.
        app_users = credentials.parse(os.environ.get("APP_USERS"))

        if not dev_mode:
            # Fail closed: an instance that can't authenticate safely must never
            # boot. Require BOTH a real signing secret and >=1 login credential,
            # so a deploy can be neither open nor impossible to log into.
            problems = []
            if not explicit_secret:
                problems.append("AUTH_JWT_SECRET must be set (no ephemeral secret outside dev)")
            if not app_users:
                problems.append(
                    "APP_USERS must define at least one 'username:hash' credential "
                    "(generate a hash with `python -m app.password`)"
                )
            if problems:
                raise RuntimeError(
                    "Auth misconfigured with AUTH_DEV_MODE off: "
                    + "; ".join(problems)
                    + ". Provide these from the host secret store, or set "
                    "AUTH_DEV_MODE=1 for the local dev loop."
                )
        else:
            # Never log the secret value itself — note only whether it's the
            # ephemeral fallback.
            _log.warning(
                "AUTH_DEV_MODE is on: dev auth active (built-in dev/dev login, %s). "
                "Never run this in production.",
                "ephemeral JWT secret" if not explicit_secret else "fixed dev secret",
            )
            # Seed the built-in dev login without clobbering an explicit entry.
            app_users.setdefault(DEV_USERNAME, hash_password(DEV_PASSWORD))

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
            # In prod ``explicit_secret`` is guaranteed set (we raised above);
            # the ephemeral fallback only ever fires in dev. Never log it.
            jwt_secret=explicit_secret or secrets.token_urlsafe(32),
            jwt_algorithm="HS256",
            session_ttl_days=int(os.environ.get("AUTH_SESSION_TTL_DAYS", "30")),
            default_tenant_id=int(os.environ.get("DEFAULT_TENANT_ID", "1")),
            dev_mode=dev_mode,
            login_throttle_max=int(os.environ.get("AUTH_LOGIN_THROTTLE_MAX", "5")),
            login_throttle_window_seconds=float(
                os.environ.get("AUTH_LOGIN_THROTTLE_WINDOW_SECONDS", "300")
            ),
            app_users=app_users,
        )


settings = Settings.from_env()
