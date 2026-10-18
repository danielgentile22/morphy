"""The users.txt file format — now an import source only (PRD #130).

Credentials live in the app database (``credentials_store``); this module
keeps the file-era pieces that survive the storage change:

* ``normalize`` — the one normalization for usernames and team names
  (trimmed + lowercased), shared by the store, the login throttle key, and
  the parser;
* ``AuthOutcome`` / ``AuthResult`` / ``CredentialEntry`` — the three-way
  authentication result and the parsed-credential shape the store reuses;
* ``parse`` / ``load`` — the ``username:hash:team`` line format, consumed by
  the one-shot migration (``python -m app.users import-file`` and the
  empty-table boot import).

One user per line: ``username:<encoded_hash>:team``. The encoded hash is the
self-describing form produced by ``password.hash_password``, whose alphabet
never contains ``:``, so a naive split is unambiguous. ``#`` lines and blank
lines are comments; malformed lines (wrong field count, missing fields) are
skipped, never fatal. A line without a team is **not** a valid credential.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

_log = logging.getLogger(__name__)


class AuthOutcome(Enum):
    UNKNOWN_USER = "unknown_user"
    WRONG_PASSWORD = "wrong_password"
    SUCCESS = "success"


@dataclass(frozen=True)
class CredentialEntry:
    """One credential (all fields normalized) — a parsed file line or a
    ``credential`` table row."""

    username: str
    encoded_hash: str
    team: str
    # Table rows only (ADR-077); the users.txt format has no such field.
    read_only: bool = False


@dataclass(frozen=True)
class AuthResult:
    outcome: AuthOutcome
    username: str | None = None  # canonical (normalized) username, set on success
    team: str | None = None  # the user's team, set on success

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
    raising. On duplicate usernames the last line wins (the bottom-most edit
    is the latest intent). Insertion order is file order — the import relies
    on that for team→tenant inheritance (#86).
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
    """Read + parse a credentials file. A missing file yields no entries.

    Never raises: an unreadable or undecodable file also yields no entries
    (logged) — a broken import source reads as "nothing to import", never a
    crash at boot.
    """
    file = Path(path)
    try:
        return parse(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError):
        _log.warning("credentials file %s could not be read; treating as empty", file)
        return {}
