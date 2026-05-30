"""Backend settings — environment-driven, fail-closed outside dev.

A database URL, the path to the static owners index, and the magic-link
auth knobs (Slice 2 / #48 — ADR-055). The default database is a local
SQLite file so the backend runs with zero external services; point
``DATABASE_URL`` at Postgres (``postgresql+psycopg://…``) in deploy/CI.

Auth posture is gated on a single switch, ``AUTH_DEV_MODE`` (default
**off** — the safe state). With it off (prod), ``from_env`` refuses to
build without a real ``AUTH_JWT_SECRET`` and a sign-in gate, and the
dev-only conveniences (raw-token echo, ephemeral secret) are forced off.
With it on, the zero-config local loop is preserved: an ephemeral
per-process secret, the raw magic-link token echoed to the SPA, and open
auto-provisioning. The real email sender + secret store land with #16.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

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
    # Forced False outside dev (see ``dev_mode``).
    expose_token_in_response: bool
    # Master safety switch. False (default) = prod posture: fail closed.
    # True = local dev: ephemeral secret + token echo + open sign-up allowed.
    dev_mode: bool
    # Explicit, named opt-in to open auto-provisioning in prod. Without it,
    # prod requires a non-empty ``allowed_emails`` (else ``from_env`` raises).
    allow_open_signup: bool
    # Per-email request-link throttle: at most ``link_rate_max`` links issued
    # per email within a rolling ``link_rate_window_minutes`` window. Guards
    # the endpoint against email-bombing and token-grinding.
    link_rate_max: int
    link_rate_window_minutes: int

    @staticmethod
    def from_env() -> Settings:
        default_db = (
            f"sqlite+pysqlite:///{PROJECT_ROOT / 'data' / 'processed' / 'lead_state.sqlite3'}"
        )
        dev_mode = _env_bool("AUTH_DEV_MODE", default=False)
        explicit_secret = os.environ.get("AUTH_JWT_SECRET")
        allowed_emails = frozenset(
            e.strip().lower()
            for e in os.environ.get("AUTH_ALLOWED_EMAILS", "").split(",")
            if e.strip()
        )
        allow_open_signup = _env_bool("AUTH_ALLOW_OPEN_SIGNUP", default=False)

        if not dev_mode:
            # Fail closed: refuse to build a prod config that can't authenticate
            # safely, rather than silently papering over it with dev defaults.
            problems = []
            if not explicit_secret:
                problems.append("AUTH_JWT_SECRET must be set (no ephemeral secret outside dev)")
            if not allowed_emails and not allow_open_signup:
                problems.append(
                    "AUTH_ALLOWED_EMAILS must be non-empty "
                    "(or set AUTH_ALLOW_OPEN_SIGNUP=1 to intentionally allow open sign-up)"
                )
            if problems:
                raise RuntimeError(
                    "Auth misconfigured with AUTH_DEV_MODE off: "
                    + "; ".join(problems)
                    + ". Provide these from the host secret store, or set "
                    "AUTH_DEV_MODE=1 for the local dev loop."
                )
        else:
            # Loud once, on the secret only if it's the ephemeral fallback —
            # never log the secret value itself.
            _log.warning(
                "AUTH_DEV_MODE is on: dev auth active (%s raw-token echo, open "
                "sign-up unless allowlisted). Never run this in production.",
                "ephemeral JWT secret," if not explicit_secret else "fixed dev secret,",
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
            # In prod ``explicit_secret`` is guaranteed set (we raised above);
            # the ephemeral fallback only ever fires in dev. Never log it.
            jwt_secret=explicit_secret or secrets.token_urlsafe(32),
            jwt_algorithm="HS256",
            session_ttl_days=int(os.environ.get("AUTH_SESSION_TTL_DAYS", "2")),
            link_ttl_minutes=int(os.environ.get("AUTH_LINK_TTL_MINUTES", "15")),
            default_tenant_id=int(os.environ.get("DEFAULT_TENANT_ID", "1")),
            allowed_emails=allowed_emails,
            # The token echo is a dev-only convenience — never honored in prod,
            # regardless of AUTH_EXPOSE_TOKEN.
            expose_token_in_response=dev_mode and _env_bool("AUTH_EXPOSE_TOKEN", default=True),
            dev_mode=dev_mode,
            allow_open_signup=allow_open_signup,
            link_rate_max=int(os.environ.get("AUTH_LINK_RATE_MAX", "5")),
            link_rate_window_minutes=int(os.environ.get("AUTH_LINK_RATE_WINDOW_MINUTES", "15")),
        )


settings = Settings.from_env()
