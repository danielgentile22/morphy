"""LeadStore behavior: persistence, status ladder, auto-logged activity."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from backend.app.lead_status import InvalidTransition
from backend.app.lead_store import LeadStore

CID = "abc123def456"


def test_new_lead_defaults_to_new(store_factory: Callable[[int], LeadStore]) -> None:
    store = store_factory(1)
    lead = store.get_or_create(CID)
    assert lead.status == "new"
    assert lead.notes == ""


def test_status_and_notes_persist_across_sessions(
    store_factory: Callable[[int], LeadStore],
) -> None:
    store_factory(1).upsert(CID, status="researching", notes="left a voicemail")

    # A fresh store/session — the "survives a reload" path.
    reloaded = store_factory(1).get_lead(CID)
    assert reloaded is not None
    assert reloaded.status == "researching"
    assert reloaded.notes == "left a voicemail"


def test_status_transition_auto_logs_an_activity_row(
    store_factory: Callable[[int], LeadStore],
) -> None:
    store = store_factory(1)
    store.upsert(CID, status="researching")

    attempts = store_factory(1).list_attempts(CID)
    assert len(attempts) == 1
    assert attempts[0].channel == "status"
    assert attempts[0].outcome == "new→researching"


def test_saving_a_note_without_status_change_logs_nothing(
    store_factory: Callable[[int], LeadStore],
) -> None:
    store = store_factory(1)
    store.upsert(CID, notes="just a note")
    assert store_factory(1).list_attempts(CID) == []


def test_walking_the_full_legal_ladder(store_factory: Callable[[int], LeadStore]) -> None:
    store = store_factory(1)
    for status in ["researching", "contacted", "interested", "in_business"]:
        store.upsert(CID, status=status)
    assert store_factory(1).get_lead(CID).status == "in_business"
    # one auto-logged row per transition
    assert len(store_factory(1).list_attempts(CID)) == 4


def test_illegal_transition_is_rejected_and_not_persisted(
    store_factory: Callable[[int], LeadStore],
) -> None:
    store = store_factory(1)
    with pytest.raises(InvalidTransition):
        store.upsert(CID, status="in_business")  # New → In Business is illegal

    # nothing was written — not even a New row gets a bogus status
    after = store_factory(1).get_lead(CID)
    assert after is None or after.status == "new"
    assert store_factory(1).list_attempts(CID) == []


def test_terminal_status_cannot_advance(store_factory: Callable[[int], LeadStore]) -> None:
    store = store_factory(1)
    store.upsert(CID, status="researching")
    store.upsert(CID, status="uninterested")
    with pytest.raises(InvalidTransition):
        store.upsert(CID, status="contacted")
