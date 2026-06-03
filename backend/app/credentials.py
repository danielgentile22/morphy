"""Credential store — parse the users file and authenticate against it (#84).

The credentials file (default ``backend/users.txt``, overridable via
``APP_USERS_FILE``) is the **only** credential source: one user per line,

    username:<encoded_hash>:team

The encoded hash is the self-describing form produced by
``password.hash_password``, whose alphabet never contains ``:``, so a naive
split is unambiguous. ``#`` lines and blank lines are comments; malformed
lines (wrong field count, missing username/hash/team) are skipped, never
fatal — one bad line can't take the whole login surface down. Usernames and
team names are normalized case-insensitively (trimmed + lowercased) on both
parse and lookup. A line without a team is **not** a valid credential.

``authenticate`` returns a three-way result — unknown-user vs wrong-password
vs success — because the product wants a *specific* sign-in error. That
trades a little username-enumeration exposure for usability; the login
throttle (#77) bounds that exposure.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .password import verify_password

_log = logging.getLogger(__name__)


class AuthOutcome(Enum):
    UNKNOWN_USER = "unknown_user"
    WRONG_PASSWORD = "wrong_password"
    SUCCESS = "success"


@dataclass(frozen=True)
class CredentialEntry:
    """One parsed ``username:hash:team`` line (all fields normalized)."""

    username: str
    encoded_hash: str
    team: str


@dataclass(frozen=True)
class AuthResult:
    outcome: AuthOutcome
    username: str | None = None  # canonical (normalized) username, set on success
    team: str | None = None  # the user's team from the file, set on success

    @property
    def ok(self) -> bool:
        return self.outcome is AuthOutcome.SUCCESS


def normalize(value: str) -> str:
    """Trim + lowercase — the one normalization for usernames and team names."""
    return value.strip().lower()


# Kept under its historical name: the login route keys its throttle on this.
normalize_username = normalize


def parse(text: str) -> dict[str, CredentialEntry]:
    """Parse credentials-file content into ``{username -> CredentialEntry}``.

    Comments (``#``), blank lines, and malformed lines are skipped rather than
    raising. On duplicate usernames the last line wins (matching "the file is
    the source of truth" — the bottom-most edit is the latest intent).
    """
    users: dict[str, CredentialEntry] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) != 3:
            continue  # wrong field count (incl. the team-less legacy shape)
        username, encoded, team = normalize(parts[0]), parts[1].strip(), normalize(parts[2])
        if not (username and encoded and team):
            continue  # a credential requires all three fields
        users[username] = CredentialEntry(username=username, encoded_hash=encoded, team=team)
    return users


def load(path: Path | str) -> dict[str, CredentialEntry]:
    """Read + parse the credentials file. A missing file yields no entries.

    Never raises: an unreadable or undecodable file also yields no entries
    (logged), so a broken file fails closed — every login gets a 401, never a
    500 from the login route.
    """
    file = Path(path)
    try:
        return parse(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError):
        _log.warning("credentials file %s could not be read; treating as empty", file)
        return {}


def authenticate(users: Mapping[str, CredentialEntry], username: str, password: str) -> AuthResult:
    """Check a username/password against the parsed credential entries."""
    canonical = normalize(username)
    entry = users.get(canonical)
    if entry is None:
        return AuthResult(AuthOutcome.UNKNOWN_USER)
    if not verify_password(password, entry.encoded_hash):
        return AuthResult(AuthOutcome.WRONG_PASSWORD)
    return AuthResult(AuthOutcome.SUCCESS, username=canonical, team=entry.team)
