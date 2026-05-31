"""Credential store — parse ``APP_USERS`` and authenticate against it.

``APP_USERS`` is a flat, comma-separated list of ``username:<encoded_hash>``
entries (the encoded hash is the self-describing form produced by
``password.hash_password``, whose alphabet never contains ``:`` or ``,``, so
a naive split is unambiguous). Usernames are normalized case-insensitively
(trimmed + lowercased) on both parse and lookup, so ``Alice `` and ``alice``
collapse to one identity.

``authenticate`` returns a three-way result — unknown-user vs wrong-password
vs success — because the product wants a *specific* sign-in error. That
trades a little username-enumeration exposure for usability; throttling that
exposure is a separate slice (#77).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .password import verify_password


class AuthOutcome(Enum):
    UNKNOWN_USER = "unknown_user"
    WRONG_PASSWORD = "wrong_password"
    SUCCESS = "success"


@dataclass(frozen=True)
class AuthResult:
    outcome: AuthOutcome
    username: str | None = None  # canonical (normalized) username, set on success

    @property
    def ok(self) -> bool:
        return self.outcome is AuthOutcome.SUCCESS


def normalize_username(username: str) -> str:
    return username.strip().lower()


def parse(raw: str | None) -> dict[str, str]:
    """Parse an ``APP_USERS`` string into a ``{username -> encoded_hash}`` map.

    Empty/malformed entries are skipped rather than raising, so one bad entry
    can't take the whole login surface down.
    """
    users: dict[str, str] = {}
    for entry in (raw or "").split(","):
        username, sep, encoded = entry.partition(":")
        if not sep:
            continue  # no ':' — not a credential entry
        username = normalize_username(username)
        encoded = encoded.strip()
        if username and encoded:
            users[username] = encoded
    return users


def authenticate(users: Mapping[str, str], username: str, password: str) -> AuthResult:
    """Check a username/password against the parsed credential map."""
    canonical = normalize_username(username)
    encoded = users.get(canonical)
    if encoded is None:
        return AuthResult(AuthOutcome.UNKNOWN_USER)
    if not verify_password(password, encoded):
        return AuthResult(AuthOutcome.WRONG_PASSWORD)
    return AuthResult(AuthOutcome.SUCCESS, username=canonical)
