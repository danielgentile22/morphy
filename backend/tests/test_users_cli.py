"""User-management CLI for the credentials file (#87, PRD #83).

The CLI is the way an administrator manages users — they never generate,
paste, or read a hash by hand. Tests drive the public command functions
(the argparse/getpass shell is a thin wrapper) plus one HTTP-level check
that a CLI-added user can really sign in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app import credentials, users
from backend.app.config import settings
from backend.app.users import UsersFileError

from ._helpers import api

SAMPLE = {
    "schema_version": 1,
    "count": 1,
    "owners": [
        {
            "display_cluster_id": "nat0000aaaa",
            "owner_name": "AMERICAN TOWERS LLC",
            "owner_name_norm": "AMERICAN TOWERS",
            "owner_kind": "llc",
            "states": ["AR"],
            "n_states": 1,
            "cross_state": False,
            "parcel_count": 1,
            "tower_count": 3,
            "solar_count": 0,
            "total_assessed_value": 1.0,
            "max_parcel_score": 0.5,
            "score": 0.5,
            "distress_tier": "at-risk",
            "in_oz": False,
            "in_qct": False,
            "persistent_poverty": False,
        }
    ],
}


@pytest.fixture
def users_file(tmp_path: Path) -> Path:
    return tmp_path / "users.txt"


# ── add ───────────────────────────────────────────────────────────────────────
def test_add_creates_a_user_who_can_authenticate(users_file: Path) -> None:
    users.add_user(users_file, "Alice", "Acme Team", "wonderland")
    loaded = credentials.load(users_file)
    assert credentials.authenticate(loaded, "alice", "wonderland").ok
    assert loaded["alice"].team == "acme team"  # normalized on write


def test_add_creates_the_file_if_missing(users_file: Path) -> None:
    assert not users_file.exists()
    users.add_user(users_file, "alice", "acme", "pw")
    assert users_file.is_file()


def test_add_duplicate_username_is_a_clear_error(users_file: Path) -> None:
    users.add_user(users_file, "alice", "acme", "pw")
    with pytest.raises(UsersFileError, match="already exists"):
        users.add_user(users_file, " ALICE ", "other-team", "pw2")
    # The file was not touched — still exactly one alice line.
    assert len(credentials.load(users_file)) == 1


def test_add_rejects_empty_username_team_or_password(users_file: Path) -> None:
    with pytest.raises(UsersFileError):
        users.add_user(users_file, "", "acme", "pw")
    with pytest.raises(UsersFileError):
        users.add_user(users_file, "alice", "  ", "pw")
    with pytest.raises(UsersFileError):
        users.add_user(users_file, "alice", "acme", "")


def test_add_rejects_a_username_containing_a_colon(users_file: Path) -> None:
    # ':' is the field separator — a username carrying one would corrupt the line.
    with pytest.raises(UsersFileError):
        users.add_user(users_file, "al:ice", "acme", "pw")
    with pytest.raises(UsersFileError):
        users.add_user(users_file, "alice", "ac:me", "pw")


# ── remove ────────────────────────────────────────────────────────────────────
def test_remove_deletes_the_user_and_keeps_everyone_else(users_file: Path) -> None:
    users.add_user(users_file, "alice", "acme", "pw-a")
    users.add_user(users_file, "bob", "acme", "pw-b")
    users.remove_user(users_file, "ALICE")  # case-insensitive match
    loaded = credentials.load(users_file)
    assert "alice" not in loaded
    assert credentials.authenticate(loaded, "bob", "pw-b").ok


def test_remove_missing_username_is_a_clear_error(users_file: Path) -> None:
    users.add_user(users_file, "alice", "acme", "pw")
    with pytest.raises(UsersFileError, match="no user"):
        users.remove_user(users_file, "ghost")


# ── list ──────────────────────────────────────────────────────────────────────
def test_list_shows_usernames_and_teams_never_hashes(users_file: Path) -> None:
    users.add_user(users_file, "alice", "acme", "pw-a")
    users.add_user(users_file, "bob", "globex", "pw-b")
    listing = users.list_users(users_file)
    assert listing == [("alice", "acme"), ("bob", "globex")]
    # Nothing hash-shaped or password-shaped in the output.
    flat = " ".join(str(x) for pair in listing for x in pair)
    assert "pbkdf2" not in flat
    assert "pw-a" not in flat


def test_list_on_a_missing_file_is_empty(users_file: Path) -> None:
    assert users.list_users(users_file) == []


# ── set-password ──────────────────────────────────────────────────────────────
def test_set_password_old_stops_working_new_works(users_file: Path) -> None:
    users.add_user(users_file, "alice", "acme", "old-pw")
    users.set_password(users_file, "alice", "new-pw")
    loaded = credentials.load(users_file)
    assert not credentials.authenticate(loaded, "alice", "old-pw").ok
    assert credentials.authenticate(loaded, "alice", "new-pw").ok
    # The team is untouched by a password change.
    assert loaded["alice"].team == "acme"


def test_set_password_for_missing_user_is_a_clear_error(users_file: Path) -> None:
    with pytest.raises(UsersFileError, match="no user"):
        users.set_password(users_file, "ghost", "pw")


# ── set-team ──────────────────────────────────────────────────────────────────
def test_set_team_moves_the_user_and_keeps_the_password(users_file: Path) -> None:
    users.add_user(users_file, "alice", "acme", "pw")
    users.set_team(users_file, "alice", "Globex Corp")
    loaded = credentials.load(users_file)
    assert loaded["alice"].team == "globex corp"
    assert credentials.authenticate(loaded, "alice", "pw").ok  # password unchanged


def test_set_team_for_missing_user_is_a_clear_error(users_file: Path) -> None:
    with pytest.raises(UsersFileError, match="no user"):
        users.set_team(users_file, "ghost", "acme")


# ── file fidelity ─────────────────────────────────────────────────────────────
def test_comments_and_line_order_survive_every_operation(users_file: Path) -> None:
    """Comments document the file and line order decides team→tenant
    inheritance (#86) — no operation may scramble either."""
    users_file.write_text(
        "# the original team must stay first (tenant 1)\n"
        f"alice:{_hash('pw-a')}:first-team\n"
        "# bob joined later\n"
        f"bob:{_hash('pw-b')}:second-team\n",
        encoding="utf-8",
    )
    users.add_user(users_file, "carol", "second-team", "pw-c")
    users.set_password(users_file, "bob", "pw-b2")
    users.set_team(users_file, "carol", "third-team")
    users.remove_user(users_file, "bob")

    text = users_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    # Both comments survived, in place.
    assert lines[0] == "# the original team must stay first (tenant 1)"
    assert "# bob joined later" in lines
    # alice (first-team) is still the first credential line.
    first_cred = next(line for line in lines if line and not line.startswith("#"))
    assert first_cred.startswith("alice:")
    assert credentials.teams_in_file_order(credentials.load(users_file))[0] == "first-team"


def test_writes_are_atomic_no_partial_file_on_crash(users_file: Path, monkeypatch) -> None:
    """A crash mid-write must never truncate or corrupt the live file."""
    users.add_user(users_file, "alice", "acme", "pw")
    before = users_file.read_text(encoding="utf-8")

    # Force the final rename step to blow up — simulating a crash after the
    # temp file is written but before it replaces the real one.
    def boom(src, dst):
        raise OSError("simulated crash")

    monkeypatch.setattr(users.os, "replace", boom)
    with pytest.raises(OSError, match="simulated crash"):
        users.add_user(users_file, "bob", "acme", "pw-b")

    monkeypatch.undo()
    # The live file is untouched and still parses.
    assert users_file.read_text(encoding="utf-8") == before
    assert list(credentials.load(users_file)) == ["alice"]
    # No leftover temp files with hash material in the directory.
    assert [p.name for p in users_file.parent.iterdir()] == ["users.txt"]


# ── end-to-end: a CLI-added user signs in over HTTP ───────────────────────────
def test_a_cli_added_user_can_sign_in_through_the_api() -> None:
    creds_path = Path(settings.credentials_path)
    original = creds_path.read_text(encoding="utf-8")
    try:
        users.add_user(creds_path, "cli-user", "devteam", "cli-password")
        with api(SAMPLE) as (client, _eng, _sender):
            r = client.post(
                "/api/auth/login", json={"username": "cli-user", "password": "cli-password"}
            )
            assert r.status_code == 200
            assert r.json()["access_token"]
    finally:
        creds_path.write_text(original, encoding="utf-8")


def _hash(password: str) -> str:
    from backend.app.password import hash_password

    return hash_password(password)
