"""DB-backed credential store — the only credential source (PRD #130).

Supersedes the ``users.txt`` *storage* of ADR-063 while preserving its
authority invariants: the ``credential`` table is consulted on **every
request** (``get``), the three-way ``authenticate`` result is unchanged
(unknown-user vs wrong-password vs success — the product wants a *specific*
sign-in error; the login throttle bounds the enumeration exposure), usernames
and team names stay normalized (trimmed + lowercased), and registration order
(``id``) replaces file order for teams-as-tenants (#86) — the first
credential's team owns tenant 1.

All functions take the caller's ``Session`` so route handlers, the CLI
(``python -m app.users``), and self-service password change share one writer
path. The CLI and the password-change route are the only sanctioned writers.

Living in the app database means Litestream's continuous replication now
covers credentials — losing the volume no longer means losing every login.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .credentials import AuthOutcome, AuthResult, CredentialEntry, normalize
from .models import Credential
from .password import hash_password, verify_password

_log = logging.getLogger(__name__)


class CredentialsError(Exception):
    """A user-facing credential-management error (bad input, missing user,
    duplicate, refused import). The CLI prints it; the API maps it to 422."""


# ── reads (login + per-request authority) ────────────────────────────────────
def get(session: Session, username: str) -> CredentialEntry | None:
    """The credential for ``username`` (normalized), or None. This is the
    per-request authority check: presence here is what authorizes a verified
    identity, on every request."""
    row = _row(session, username)
    if row is None:
        return None
    return CredentialEntry(username=row.username, encoded_hash=row.password_hash, team=row.team)


def authenticate(session: Session, username: str, password: str) -> AuthResult:
    """Check a username/password — the same three-way result the file-era
    parser produced."""
    entry = get(session, username)
    if entry is None:
        return AuthResult(AuthOutcome.UNKNOWN_USER)
    if not verify_password(password, entry.encoded_hash):
        return AuthResult(AuthOutcome.WRONG_PASSWORD)
    return AuthResult(AuthOutcome.SUCCESS, username=entry.username, team=entry.team)


def teams_in_order(session: Session) -> list[str]:
    """Unique team names in first-appearance (registration) order.

    The order matters: teams are find-or-created in this order (#86), which
    is what guarantees the first registered team owns tenant 1 and inherits
    the pre-teams lead board. ``id`` order replaces file order."""
    rows = session.scalars(select(Credential.team).order_by(Credential.id))
    return list(dict.fromkeys(rows))


def count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Credential)) or 0


def list_users(session: Session) -> list[tuple[str, str]]:
    """``(username, team)`` pairs in registration order — never hashes."""
    rows = session.scalars(select(Credential).order_by(Credential.id))
    return [(r.username, r.team) for r in rows]


# ── writers (the CLI + self-service password change only) ────────────────────
def add(session: Session, username: str, team: str, password: str) -> None:
    """Insert a new credential. The new user can sign in immediately."""
    username_n, team_n = _valid_username(username), _valid_team(team)
    if not password:
        raise CredentialsError("password must not be empty")
    if _row(session, username_n) is not None:
        raise CredentialsError(
            f"user '{username_n}' already exists (use set-password / set-team to change it)"
        )
    session.add(Credential(username=username_n, password_hash=hash_password(password), team=team_n))
    session.commit()


def remove(session: Session, username: str) -> None:
    """Delete a user's credential. Their next request fails (per-request
    authority — no session wait-out)."""
    session.delete(_require_row(session, username))
    session.commit()


def set_password(session: Session, username: str, password: str) -> None:
    """Replace a user's hash (their row keeps its id, so team→tenant
    registration order is untouched)."""
    if not password:
        raise CredentialsError("password must not be empty")
    row = _require_row(session, username)
    row.password_hash = hash_password(password)
    session.commit()


def set_team(session: Session, username: str, team: str) -> None:
    """Move a user to another team (their row keeps its id and password)."""
    row = _require_row(session, username)
    row.team = _valid_team(team)
    session.commit()


def change_password(session: Session, username: str, current: str, new: str) -> bool:
    """Self-service password change (PRD #121): verify ``current``, then
    rotate. Returns False (and writes nothing) on a wrong current password;
    raises ``CredentialsError`` for an unknown user or an empty new password.
    The one sanctioned runtime writer besides the CLI."""
    row = _require_row(session, username)
    if not verify_password(current, row.password_hash):
        return False
    set_password(session, username, new)
    return True


def import_entries(session: Session, entries: list[CredentialEntry]) -> int:
    """One-shot migration (PRD #130): insert parsed users.txt entries in file
    order, preserving team→tenant inheritance (#86). Refuses to run over an
    already-populated table — the import is a cutover, never a merge."""
    existing = count(session)
    if existing:
        raise CredentialsError(
            f"credentials table already has {existing} row(s) — refusing to import over them"
        )
    for entry in entries:
        session.add(
            Credential(username=entry.username, password_hash=entry.encoded_hash, team=entry.team)
        )
    session.commit()
    return len(entries)


# ── fail-closed boot (ADR-069, preserving the ADR-062/063 posture) ───────────
def ensure_fail_closed_boot(eng=None, cfg=None) -> None:
    """Refuse to serve when auth can't work — keyed on the DB.

    Called from the app's lifespan after ``init_db``. Outside dev mode it
    requires a real signing secret AND at least one credential row, so a
    deploy can be neither open nor impossible to log into. In dev mode an
    empty table seeds the built-in ``dev``/``dev`` login through the same
    ``add`` path the CLI uses — dev cannot bypass the production code path.
    """
    from .config import DEV_PASSWORD, DEV_TEAM, DEV_USERNAME, settings

    cfg = cfg or settings
    if eng is None:
        from .db import engine as default_engine

        eng = default_engine

    problems: list[str] = []
    if not cfg.dev_mode and cfg.jwt_secret_is_ephemeral:
        problems.append("AUTH_JWT_SECRET must be set (no ephemeral secret outside dev)")

    with Session(bind=eng) as session:
        if count(session) == 0:
            if cfg.dev_mode:
                add(session, DEV_USERNAME, DEV_TEAM, DEV_PASSWORD)
                _log.warning(
                    "AUTH_DEV_MODE: seeded the built-in %s/%s login (ephemeral dev credential).",
                    DEV_USERNAME,
                    DEV_PASSWORD,
                )
            else:
                problems.append(
                    "no credentials exist — add one with `python -m app.users add "
                    "<username> <team>`, or migrate a legacy users.txt with "
                    "`python -m app.users import-file <path>`"
                )

    if problems:
        raise RuntimeError(
            "Auth misconfigured with AUTH_DEV_MODE off: "
            + "; ".join(problems)
            + ". Provide these from the host secret store, or set AUTH_DEV_MODE=1 "
            "for the local dev loop."
        )


# ── helpers ───────────────────────────────────────────────────────────────────
def _row(session: Session, username: str) -> Credential | None:
    stmt = select(Credential).where(Credential.username == normalize(username))
    return session.scalars(stmt).first()


def _require_row(session: Session, username: str) -> Credential:
    row = _row(session, username)
    if row is None:
        raise CredentialsError(f"no user '{normalize(username)}'")
    return row


def _valid_username(username: str) -> str:
    name = normalize(username)
    if not name:
        raise CredentialsError("username must not be empty")
    if ":" in name:
        # Kept from the file era: ':' was the field separator, and import/export
        # of users.txt-shaped lines must stay round-trippable.
        raise CredentialsError("username must not contain ':'")
    return name


def _valid_team(team: str) -> str:
    name = normalize(team)
    if not name:
        raise CredentialsError("team must not be empty")
    if ":" in name:
        raise CredentialsError("team must not contain ':'")
    return name
