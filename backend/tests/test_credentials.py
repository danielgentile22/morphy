"""Unit tests for users.txt parsing (#84; import-source-only since PRD #130).

The file format survives as the one-shot migration source (``python -m
app.users import-file`` + the empty-table boot import): one
``username:hash:team`` line per user, ``#`` comments, malformed lines
skipped. Usernames and teams are normalized (trimmed + lowercased). A line
without a team is not a valid credential. Authentication itself now lives in
``credentials_store`` (see test_credentials_store.py).
"""

from __future__ import annotations

from pathlib import Path

from backend.app import credentials
from backend.app.password import hash_password, verify_password


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
    assert verify_password("new", users["alice"].encoded_hash)
    assert not verify_password("old", users["alice"].encoded_hash)


def test_parse_preserves_file_order(tmp_path: Path) -> None:
    # The import relies on insertion order = file order for team→tenant
    # inheritance (#86): the first team in the file must register first.
    f = _write(
        tmp_path,
        f"zed:{hash_password('z')}:last-alphabetically-first-in-file",
        f"alice:{hash_password('a')}:acme",
    )
    assert list(credentials.load(f)) == ["zed", "alice"]
