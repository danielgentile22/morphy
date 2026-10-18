"""The DB-backed credential store (PRD #130) — the port of the credential
semantics the file parser used to own.

One ``credential`` row per user; usernames and teams normalized (trimmed +
lowercased) on write and lookup; the three-way ``authenticate`` result
(unknown-user vs wrong-password vs success) unchanged; registration order
(``id``) replaces file order for teams-as-tenants (#86). The management
functions here are the same writers the CLI shell drives.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from backend.app import credentials_store as store
from backend.app.credentials import AuthOutcome, CredentialEntry, parse
from backend.app.credentials_store import CredentialsError
from backend.app.password import hash_password, verify_password


@pytest.fixture
def session(engine) -> Session:
    return Session(bind=engine, future=True)


# ── add + authenticate ────────────────────────────────────────────────────────
def test_add_creates_a_user_who_can_authenticate(session: Session) -> None:
    store.add(session, "Alice", "Acme Team", "wonderland")
    result = store.authenticate(session, "ALICE", "wonderland")
    assert result.outcome is AuthOutcome.SUCCESS
    assert result.ok
    assert result.username == "alice"  # normalized on write and lookup
    assert result.team == "acme team"


def test_wrong_password_and_unknown_user_are_distinguishable(session: Session) -> None:
    store.add(session, "alice", "acme", "pw1")
    assert store.authenticate(session, "alice", "bad").outcome is AuthOutcome.WRONG_PASSWORD
    assert store.authenticate(session, "carol", "pw1").outcome is AuthOutcome.UNKNOWN_USER


def test_authenticating_against_an_empty_store_is_unknown_user(session: Session) -> None:
    assert store.authenticate(session, "anyone", "x").outcome is AuthOutcome.UNKNOWN_USER


def test_add_duplicate_username_is_a_clear_error(session: Session) -> None:
    store.add(session, "alice", "acme", "pw")
    with pytest.raises(CredentialsError, match="already exists"):
        store.add(session, " ALICE ", "other-team", "pw2")
    assert store.count(session) == 1  # nothing written


def test_add_rejects_empty_username_team_or_password(session: Session) -> None:
    with pytest.raises(CredentialsError):
        store.add(session, "", "acme", "pw")
    with pytest.raises(CredentialsError):
        store.add(session, "alice", "  ", "pw")
    with pytest.raises(CredentialsError):
        store.add(session, "alice", "acme", "")


def test_add_rejects_a_colon_in_username_or_team(session: Session) -> None:
    # ':' was the file's field separator; import/export of users.txt-shaped
    # lines must stay round-trippable.
    with pytest.raises(CredentialsError):
        store.add(session, "al:ice", "acme", "pw")
    with pytest.raises(CredentialsError):
        store.add(session, "alice", "ac:me", "pw")


# ── per-request authority read ────────────────────────────────────────────────
def test_get_returns_the_normalized_entry_or_none(session: Session) -> None:
    store.add(session, "alice", "acme", "pw")
    entry = store.get(session, "  ALICE  ")
    assert entry is not None
    assert entry.username == "alice"
    assert entry.team == "acme"
    assert verify_password("pw", entry.encoded_hash)
    assert store.get(session, "ghost") is None


# ── remove ────────────────────────────────────────────────────────────────────
def test_remove_deletes_the_user_and_keeps_everyone_else(session: Session) -> None:
    store.add(session, "alice", "acme", "pw-a")
    store.add(session, "bob", "acme", "pw-b")
    store.remove(session, "ALICE")  # case-insensitive match
    assert store.get(session, "alice") is None
    assert store.authenticate(session, "bob", "pw-b").ok


def test_remove_missing_username_is_a_clear_error(session: Session) -> None:
    with pytest.raises(CredentialsError, match="no user"):
        store.remove(session, "ghost")


# ── list ──────────────────────────────────────────────────────────────────────
def test_list_shows_usernames_and_teams_never_hashes(session: Session) -> None:
    store.add(session, "alice", "acme", "pw-a")
    store.add(session, "bob", "globex", "pw-b")
    listing = store.list_users(session)
    assert listing == [("alice", "acme", False), ("bob", "globex", False)]
    flat = " ".join(str(x) for row in listing for x in row)
    assert "pbkdf2" not in flat
    assert "pw-a" not in flat


def test_list_on_an_empty_store_is_empty(session: Session) -> None:
    assert store.list_users(session) == []


# ── set-password ──────────────────────────────────────────────────────────────
def test_set_password_old_stops_working_new_works(session: Session) -> None:
    store.add(session, "alice", "acme", "old-pw")
    store.set_password(session, "alice", "new-pw")
    assert not store.authenticate(session, "alice", "old-pw").ok
    assert store.authenticate(session, "alice", "new-pw").ok
    entry = store.get(session, "alice")
    assert entry is not None and entry.team == "acme"  # team untouched


def test_set_password_for_missing_user_is_a_clear_error(session: Session) -> None:
    with pytest.raises(CredentialsError, match="no user"):
        store.set_password(session, "ghost", "pw")


# ── set-team ──────────────────────────────────────────────────────────────────
def test_set_team_moves_the_user_and_keeps_the_password(session: Session) -> None:
    store.add(session, "alice", "acme", "pw")
    store.set_team(session, "alice", "Globex Corp")
    entry = store.get(session, "alice")
    assert entry is not None and entry.team == "globex corp"
    assert store.authenticate(session, "alice", "pw").ok  # password unchanged


def test_set_team_for_missing_user_is_a_clear_error(session: Session) -> None:
    with pytest.raises(CredentialsError, match="no user"):
        store.set_team(session, "ghost", "acme")


# ── registration order (the file-order successor, #86) ───────────────────────
def test_teams_in_order_is_first_appearance_registration_order(session: Session) -> None:
    store.add(session, "alice", "team-b", "a")
    store.add(session, "bob", "team-a", "b")
    store.add(session, "carol", "team-b", "c")  # team-b already seen
    assert store.teams_in_order(session) == ["team-b", "team-a"]


def test_password_and_team_edits_do_not_reorder_teams(session: Session) -> None:
    # A row keeps its id through edits, so team→tenant inheritance is stable
    # (the file-era equivalent: a line kept its position).
    store.add(session, "alice", "first-team", "pw-a")
    store.add(session, "bob", "second-team", "pw-b")
    store.set_password(session, "alice", "pw-a2")
    assert store.teams_in_order(session)[0] == "first-team"


# ── one-shot import (the migration, PRD #130) ─────────────────────────────────
def _entries(*lines: str) -> list[CredentialEntry]:
    return list(parse("\n".join(lines)).values())


def test_import_preserves_file_order_and_login_outcomes(session: Session) -> None:
    entries = _entries(
        f"alice:{hash_password('pw-a')}:first-team",
        f"bob:{hash_password('pw-b')}:second-team",
    )
    assert store.import_entries(session, entries) == 2
    # Identical login outcomes to the file era…
    assert store.authenticate(session, "alice", "pw-a").ok
    assert store.authenticate(session, "bob", "pw-b").ok
    assert store.authenticate(session, "alice", "wrong").outcome is AuthOutcome.WRONG_PASSWORD
    # …and the first team in the file stays the first registered team.
    assert store.teams_in_order(session) == ["first-team", "second-team"]


def test_import_refuses_a_non_empty_table(session: Session) -> None:
    store.add(session, "existing", "acme", "pw")
    with pytest.raises(CredentialsError, match="refusing to import"):
        store.import_entries(session, _entries(f"alice:{hash_password('x')}:t"))
    assert store.count(session) == 1  # the cutover never merges
