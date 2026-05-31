"""Unit tests for APP_USERS parsing + authentication (Slice 1 / #76)."""

from __future__ import annotations

from backend.app import credentials
from backend.app.credentials import AuthOutcome
from backend.app.password import hash_password


def _store(**users: str) -> dict[str, str]:
    return {name: hash_password(pw) for name, pw in users.items()}


def test_correct_credentials_return_the_canonical_username() -> None:
    store = _store(alice="pw1")
    result = credentials.authenticate(store, "ALICE", "pw1")
    assert result.outcome is AuthOutcome.SUCCESS
    assert result.ok
    assert result.username == "alice"


def test_wrong_password_and_unknown_user_are_distinguishable() -> None:
    store = _store(alice="pw1")
    assert credentials.authenticate(store, "alice", "bad").outcome is AuthOutcome.WRONG_PASSWORD
    assert credentials.authenticate(store, "carol", "pw1").outcome is AuthOutcome.UNKNOWN_USER


def test_parse_is_case_insensitive_and_trimmed() -> None:
    store = credentials.parse(f"  Alice :{hash_password('pw1')} ")
    assert list(store) == ["alice"]
    assert credentials.authenticate(store, "alice", "pw1").ok


def test_parse_skips_empty_and_malformed_entries() -> None:
    raw = f"alice:{hash_password('pw1')},,no_colon_here,  ,bob:{hash_password('pw2')}"
    store = credentials.parse(raw)
    assert sorted(store) == ["alice", "bob"]


def test_empty_or_none_env_yields_an_empty_map() -> None:
    assert credentials.parse("") == {}
    assert credentials.parse(None) == {}
    # Authenticating against an empty store is always unknown-user.
    assert credentials.authenticate({}, "anyone", "x").outcome is AuthOutcome.UNKNOWN_USER
