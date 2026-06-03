"""Backend settings — environment-driven, fail-closed outside dev.

A database URL, the path to the static owners index, and the
username/password auth knobs (Slice 1 / #76 — ADR-055). The default
database is a local SQLite file so the backend runs with zero external
services; point ``DATABASE_URL`` at Postgres (``postgresql+psycopg://…``)
in deploy/CI.

Credentials live in a git-ignored plain-text file (#84, PRD #83): one
``username:hash:team`` line per user, default ``backend/users.txt``,
overridable via ``APP_USERS_FILE`` (production secret stores can mount
files). The old ``APP_USERS`` env var is gone — the file is the one source
of truth.

Auth posture is gated on a single switch, ``AUTH_DEV_MODE`` (default
**off** — the safe state). With it off (prod), ``from_env`` refuses to
build without a real ``AUTH_JWT_SECRET`` **and** a credentials file with at
least one valid entry — so a deploy can be neither open nor impossible to
log into. With it on, the zero-config local loop is preserved: an ephemeral
per-process secret and a built-in ``dev``/``dev`` login seeded **through the
same file-parsing code path** (a temp credentials file), so dev mode cannot
hide parsing bugs. The real secret store lands with #16.
"""

from __future__ import annotations

import logging
import os
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import credentials
from .password import hash_password

_log = logging.getLogger(__name__)

# Zero-config dev credential, written to a temp credentials file when
# AUTH_DEV_MODE is on and the configured file has no valid entry — so local
# runs and CI need no setup. Not a secret — it only unlocks the ephemeral,
# dev-only JWT secret.
DEV_USERNAME = "dev"
DEV_PASSWORD = "dev"
DEV_TEAM = "dev"

# repo root = backend/app/config.py → parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSITE_ROOT = PROJECT_ROOT / "data" / "processed" / "composite"

# The real credentials file lives in the backend directory (git-ignored; a
# committed users.txt.example documents the format).
DEFAULT_CREDENTIALS_PATH = PROJECT_ROOT / "backend" / "users.txt"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _write_dev_credentials_file() -> Path:
    """Seed the built-in dev login into a temp credentials file.

    Dev mode goes through the exact same file-parsing path as production
    (PRD #83 user story 28) — never an in-memory shortcut that could hide
    parsing bugs."""
    fd, name = tempfile.mkstemp(prefix="pilot-dev-users-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("# AUTH_DEV_MODE built-in dev credential (ephemeral; not a secret)\n")
        f.write(f"{DEV_USERNAME}:{hash_password(DEV_PASSWORD)}:{DEV_TEAM}\n")
    return Path(name)


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
    # The credentials file (#84): ``username:hash:team`` lines, the only
    # credential source. Login re-reads it, so edits apply without restart.
    credentials_path: Path

    @staticmethod
    def from_env() -> Settings:
        default_db = (
            f"sqlite+pysqlite:///{PROJECT_ROOT / 'data' / 'processed' / 'lead_state.sqlite3'}"
        )
        dev_mode = _env_bool("AUTH_DEV_MODE", default=False)
        explicit_secret = os.environ.get("AUTH_JWT_SECRET")
        credentials_path = Path(os.environ.get("APP_USERS_FILE", str(DEFAULT_CREDENTIALS_PATH)))

        if not dev_mode:
            # Fail closed: an instance that can't authenticate safely must never
            # boot. Require BOTH a real signing secret and a credentials file
            # with >=1 valid entry, so a deploy can be neither open nor
            # impossible to log into.
            problems = []
            if not explicit_secret:
                problems.append("AUTH_JWT_SECRET must be set (no ephemeral secret outside dev)")
            if not credentials.load(credentials_path):
                problems.append(
                    f"credentials file {credentials_path} must exist and contain at least "
                    "one valid 'username:hash:team' line "
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
            # Seed the built-in dev login unless the configured file already
            # has a valid credential — through the same file-parsing path.
            if not credentials.load(credentials_path):
                credentials_path = _write_dev_credentials_file()

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
            credentials_path=credentials_path,
        )


settings = Settings.from_env()
