"""Backend settings — environment-driven, with dev-friendly defaults.

A database URL, the path to the static owners index, and the magic-link
auth knobs (Slice 2 / #48 — ADR-055). The default database is a local
SQLite file so the backend runs with zero external services; point
``DATABASE_URL`` at Postgres (``postgresql+psycopg://…``) in deploy/CI.

Secrets: ``AUTH_JWT_SECRET`` comes from the host's secret store in
deploy (#16) and is never committed. In dev it falls back to an
ephemeral per-process random value (sessions don't survive a restart —
acceptable locally, never in prod).
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

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
    link_ttl_minutes: int
    # New users land in this tenant — realizes ADR-055's "reads 1 for now"
    # without a hardcoded tenant on the request path (the tenant now rides
    # on the authenticated JWT). A second tenant is a row add, not a refactor.
    default_tenant_id: int
    # Optional sign-in allowlist (comma-separated emails). Empty = open
    # auto-provisioning into the default tenant (dev). Production gates
    # sign-in behind the real sender + an allowlist/invite (#16).
    allowed_emails: frozenset[str]
    # Dev convenience: return the raw magic-link token in the request-link
    # response so the SPA can complete the exchange without a real inbox.
    # MUST be False in prod (the real email sender lands with #16).
    expose_token_in_response: bool

    @staticmethod
    def from_env() -> Settings:
        default_db = (
            f"sqlite+pysqlite:///{PROJECT_ROOT / 'data' / 'processed' / 'lead_state.sqlite3'}"
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
            # An unset secret → ephemeral random (dev only); never log it.
            jwt_secret=os.environ.get("AUTH_JWT_SECRET") or secrets.token_urlsafe(32),
            jwt_algorithm="HS256",
            session_ttl_days=int(os.environ.get("AUTH_SESSION_TTL_DAYS", "7")),
            link_ttl_minutes=int(os.environ.get("AUTH_LINK_TTL_MINUTES", "15")),
            default_tenant_id=int(os.environ.get("DEFAULT_TENANT_ID", "1")),
            allowed_emails=frozenset(
                e.strip().lower()
                for e in os.environ.get("AUTH_ALLOWED_EMAILS", "").split(",")
                if e.strip()
            ),
            expose_token_in_response=_env_bool("AUTH_EXPOSE_TOKEN", default=True),
        )


settings = Settings.from_env()
