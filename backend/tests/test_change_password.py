"""Self-service password change (PRD #121) — the most adversarial path.

``users.change_password`` is the one sanctioned runtime caller of the store's
password writer (PRD #130 moved the storage from users.txt to the credential
table; the semantics are unchanged): it verifies the current password, then
rotates the hash in place — team and registration order untouched. A wrong
current password (or an empty new one) must write nothing.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from backend.app import credentials_store as store
from backend.app import users
from backend.app.credentials_store import CredentialsError
from backend.app.users import ChangePasswordOutcome


@pytest.fixture
def session(engine) -> Session:
    return Session(bind=engine, future=True)


def test_correct_current_rotates_the_hash(session: Session) -> None:
    store.add(session, "alice", "acme", "old-pw")
    outcome = users.change_password(session, "alice", "old-pw", "new-pw")
    assert outcome is ChangePasswordOutcome.OK

    assert store.authenticate(session, "alice", "new-pw").ok
    assert not store.authenticate(session, "alice", "old-pw").ok


def test_wrong_current_is_rejected_and_nothing_changes(session: Session) -> None:
    store.add(session, "alice", "acme", "old-pw")
    before = store.get(session, "alice")
    assert before is not None

    outcome = users.change_password(session, "alice", "WRONG", "new-pw")

    assert outcome is ChangePasswordOutcome.WRONG_CURRENT
    after = store.get(session, "alice")
    assert after is not None
    assert after.encoded_hash == before.encoded_hash  # not even re-hashed
    assert store.authenticate(session, "alice", "old-pw").ok  # old still works


def test_empty_new_password_is_rejected_and_nothing_changes(session: Session) -> None:
    store.add(session, "alice", "acme", "old-pw")
    before = store.get(session, "alice")
    assert before is not None

    with pytest.raises(CredentialsError):
        users.change_password(session, "alice", "old-pw", "")

    after = store.get(session, "alice")
    assert after is not None
    assert after.encoded_hash == before.encoded_hash


def test_unknown_user_raises(session: Session) -> None:
    store.add(session, "alice", "acme", "old-pw")
    with pytest.raises(CredentialsError):
        users.change_password(session, "ghost", "x", "y")


def test_team_and_registration_order_survive_a_password_change(session: Session) -> None:
    # bob is first → his team owns tenant 1; that must not move when alice
    # (registered second) rotates her password. Other rows are untouched.
    store.add(session, "bob", "team-rocket", "bob-pw")
    store.add(session, "alice", "team-plasma", "old-pw")
    store.add(session, "carol", "team-rocket", "carol-pw")
    bob_before = store.get(session, "bob")
    assert bob_before is not None

    users.change_password(session, "alice", "old-pw", "new-pw")

    assert store.teams_in_order(session) == ["team-rocket", "team-plasma"]
    alice = store.get(session, "alice")
    assert alice is not None and alice.team == "team-plasma"
    bob_after = store.get(session, "bob")
    assert bob_after is not None
    assert bob_after.encoded_hash == bob_before.encoded_hash  # hash untouched
