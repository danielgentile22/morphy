"""Unit tests for credentials-file parsing + authentication (#84, PRD #83).

The credentials file is the only credential source: one ``username:hash:team``
line per user, ``#`` comments, malformed lines skipped. Usernames and teams
are normalized (trimmed + lowercased). A line without a team is not a valid
credential.
"""

from __future__ import annotations

from pathlib import Path

from backend.app import credentials
from backend.app.credentials import AuthOutcome
from backend.app.password import hash_password


def _write(tmp_path: Path, *lines: str) -> Path:
    f = tmp_path / "users.txt"
    f.write_text("\n".join(lines) + "\n")
    return f


# ── file parsing ──────────────────────────────────────────────────────────────
def test_valid_line_parses_to_a_normalized_entry(tmp_path: Path) -> None:
    f = _write(tmp_path, f"  Alice :{hash_password('pw1')}: Acme Team ")
    users = credentials.load(f)
    assert list(users) == ["alice"]
    assert users["alice"].team == "acme team"


def test_comments_and_blank_lines_are_skipped(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        "# header comment",
        "",
        f"alice:{hash_password('pw1')}:acme",
        "   ",
        "# trailing comment",
    )
    assert sorted(credentials.load(f)) == ["alice"]


def test_malformed_lines_are_skipped_not_fatal(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        "no-colons-at-all",
        "too:many:colons:here:extra",
        f"alice:{hash_password('pw1')}:acme",
        ":missing-username:team",
        "bob::empty-hash",
    )
    assert sorted(credentials.load(f)) == ["alice"]


def test_line_without_a_team_is_not_a_valid_credential(tmp_path: Path) -> None:
    # The pre-teams APP_USERS shape (username:hash) must not count — the team
    # field is required for a line to be a credential (#84 locks the format).
    f = _write(
        tmp_path,
        f"alice:{hash_password('pw1')}",
        f"bob:{hash_password('pw2')}:",
        f"carol:{hash_password('pw3')}:acme",
    )
    assert sorted(credentials.load(f)) == ["carol"]


def test_missing_or_empty_file_yields_no_entries(tmp_path: Path) -> None:
    assert credentials.load(tmp_path / "does-not-exist.txt") == {}
    empty = tmp_path / "users.txt"
    empty.write_text("")
    assert credentials.load(empty) == {}


def test_undecodable_file_yields_no_entries_not_a_crash(tmp_path: Path) -> None:
    # A corrupt (non-UTF-8) file must fail closed — no entries, never an
    # exception that would turn a login attempt into a 500.
    corrupt = tmp_path / "users.txt"
    corrupt.write_bytes(b"\xff\xfe broken \x80 bytes")
    assert credentials.load(corrupt) == {}


def test_duplicate_usernames_last_line_wins(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        f"alice:{hash_password('old')}:team-one",
        f"ALICE:{hash_password('new')}:team-two",
    )
    users = credentials.load(f)
    assert list(users) == ["alice"]
    assert users["alice"].team == "team-two"
    assert credentials.authenticate(users, "alice", "new").ok
    assert not credentials.authenticate(users, "alice", "old").ok


# ── authentication ────────────────────────────────────────────────────────────
def test_correct_credentials_return_username_and_team(tmp_path: Path) -> None:
    f = _write(tmp_path, f"alice:{hash_password('pw1')}:acme")
    result = credentials.authenticate(credentials.load(f), "ALICE", "pw1")
    assert result.outcome is AuthOutcome.SUCCESS
    assert result.ok
    assert result.username == "alice"
    assert result.team == "acme"


def test_wrong_password_and_unknown_user_are_distinguishable(tmp_path: Path) -> None:
    f = _write(tmp_path, f"alice:{hash_password('pw1')}:acme")
    users = credentials.load(f)
    assert credentials.authenticate(users, "alice", "bad").outcome is AuthOutcome.WRONG_PASSWORD
    assert credentials.authenticate(users, "carol", "pw1").outcome is AuthOutcome.UNKNOWN_USER


def test_authenticating_against_no_entries_is_unknown_user() -> None:
    assert credentials.authenticate({}, "anyone", "x").outcome is AuthOutcome.UNKNOWN_USER
