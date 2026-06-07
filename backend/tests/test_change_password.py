"""Self-service password change (PRD #121) — the most adversarial path.

``users.change_password`` is the one sanctioned runtime caller of the atomic
``set_password`` writer: it verifies the current password, then rewrites the
line *in place* (preserving team + file order, byte-preserving everyone else),
and bumps mtime so the per-request ``CredentialsFile`` cache reloads. A wrong
current password (or an empty new one) must leave the file byte-for-byte
unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app import credentials, users
from backend.app.users import ChangePasswordOutcome, UsersFileError


@pytest.fixture
def users_file(tmp_path: Path) -> Path:
    return tmp_path / "users.txt"


def test_correct_current_rotates_the_hash(users_file: Path) -> None:
    users.add_user(users_file, "alice", "acme", "old-pw")
    outcome = users.change_password(users_file, "alice", "old-pw", "new-pw")
    assert outcome is ChangePasswordOutcome.OK

    loaded = credentials.load(users_file)
    assert credentials.authenticate(loaded, "alice", "new-pw").ok
    assert not credentials.authenticate(loaded, "alice", "old-pw").ok


def test_wrong_current_is_rejected_and_file_is_byte_unchanged(users_file: Path) -> None:
    users.add_user(users_file, "alice", "acme", "old-pw")
    before = users_file.read_bytes()

    outcome = users.change_password(users_file, "alice", "WRONG", "new-pw")

    assert outcome is ChangePasswordOutcome.WRONG_CURRENT
    assert users_file.read_bytes() == before  # not even rewritten with the same hash
    # The old password still works — nothing changed.
    assert credentials.authenticate(credentials.load(users_file), "alice", "old-pw").ok


def test_empty_new_password_is_rejected_and_file_is_byte_unchanged(users_file: Path) -> None:
    users.add_user(users_file, "alice", "acme", "old-pw")
    before = users_file.read_bytes()

    with pytest.raises(UsersFileError):
        users.change_password(users_file, "alice", "old-pw", "")

    assert users_file.read_bytes() == before


def test_unknown_user_raises(users_file: Path) -> None:
    users.add_user(users_file, "alice", "acme", "old-pw")
    with pytest.raises(UsersFileError):
        users.change_password(users_file, "nobody", "whatever", "new-pw")


def test_line_keeps_its_position_and_team_and_others_are_byte_preserved(
    users_file: Path,
) -> None:
    # bob is first → his team owns tenant 1; that must not move when alice (the
    # 2nd line) rotates her password.
    users.add_user(users_file, "bob", "team-rocket", "bob-pw")
    users.add_user(users_file, "alice", "team-plasma", "old-pw")
    users.add_user(users_file, "carol", "team-rocket", "carol-pw")

    lines_before = users_file.read_text().splitlines()

    users.change_password(users_file, "alice", "old-pw", "new-pw")

    lines_after = users_file.read_text().splitlines()
    # Same number of lines, same order of usernames + teams.
    assert len(lines_after) == len(lines_before) == 3
    assert [line.split(":")[0] for line in lines_after] == ["bob", "alice", "carol"]
    assert [line.split(":")[2] for line in lines_after] == [
        "team-rocket",
        "team-plasma",
        "team-rocket",
    ]
    # alice's team is preserved; only her hash (field 1) changed.
    assert lines_after[1].split(":")[2] == "team-plasma"
    assert lines_after[1].split(":")[1] != lines_before[1].split(":")[1]
    # bob and carol are byte-for-byte identical (hashes untouched).
    assert lines_after[0] == lines_before[0]
    assert lines_after[2] == lines_before[2]


def test_change_bumps_mtime_so_the_per_request_cache_reloads(users_file: Path) -> None:
    users.add_user(users_file, "alice", "acme", "old-pw")
    cf = credentials.CredentialsFile(users_file)
    cached = cf.current()  # primes the (mtime_ns, size) signature cache
    assert credentials.authenticate(cached, "alice", "old-pw").ok

    assert (
        users.change_password(users_file, "alice", "old-pw", "new-pw") is ChangePasswordOutcome.OK
    )

    reloaded = cf.current()  # must re-read: the atomic rename bumped mtime
    assert credentials.authenticate(reloaded, "alice", "new-pw").ok
    assert not credentials.authenticate(reloaded, "alice", "old-pw").ok
