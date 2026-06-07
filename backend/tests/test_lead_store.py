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


def test_in_business_is_the_one_true_terminal(store_factory: Callable[[int], LeadStore]) -> None:
    store = store_factory(1)
    for status in ["researching", "contacted", "interested", "in_business"]:
        store.upsert(CID, status=status)
    # won is a dead end — no move out (not even back to interested).
    with pytest.raises(InvalidTransition):
        store.upsert(CID, status="interested")


def test_uninterested_can_be_reopened(store_factory: Callable[[int], LeadStore]) -> None:
    store = store_factory(1)
    store.upsert(CID, status="researching")
    store.upsert(CID, status="uninterested")
    # a lost/parked lead reopens to any status — here back to contacted — so a
    # mis-classification is never stranded.
    store.upsert(CID, status="contacted")
    assert store_factory(1).get_lead(CID).status == "contacted"
    # the reopen auto-logs a status-change row like any other transition.
    rows = store_factory(1).list_attempts(CID)
    assert any(a.outcome == "uninterested→contacted" for a in rows)


# ── contact fields (Slice 3 / #49) ───────────────────────────────────────────
def test_contact_fields_persist_across_sessions(
    store_factory: Callable[[int], LeadStore],
) -> None:
    store_factory(1).upsert(
        CID,
        contact={
            "contact_name": "Jane Roe",
            "contact_phone": "555-0100",
            "contact_email": "jane@example.com",
            "best_channel": "phone",
        },
    )
    reloaded = store_factory(1).get_lead(CID)
    assert reloaded is not None
    assert reloaded.contact_name == "Jane Roe"
    assert reloaded.contact_phone == "555-0100"
    assert reloaded.contact_email == "jane@example.com"
    assert reloaded.best_channel == "phone"
    # A contact edit is not a status change → nothing auto-logged.
    assert store_factory(1).list_attempts(CID) == []


def test_partial_contact_update_leaves_other_fields_untouched(
    store_factory: Callable[[int], LeadStore],
) -> None:
    store_factory(1).upsert(CID, contact={"contact_name": "First Last"})
    store_factory(1).upsert(CID, contact={"contact_phone": "555-0101"})
    lead = store_factory(1).get_lead(CID)
    assert (lead.contact_name, lead.contact_phone) == ("First Last", "555-0101")


def test_new_lead_has_empty_contact_fields(store_factory: Callable[[int], LeadStore]) -> None:
    lead = store_factory(1).get_or_create(CID)
    assert lead.contact_name == ""
    assert lead.best_channel == ""


def test_append_attempt_logs_a_manual_row(store_factory: Callable[[int], LeadStore]) -> None:
    store_factory(1).append_attempt(CID, channel="phone", outcome="left voicemail")
    attempts = store_factory(1).list_attempts(CID)
    assert len(attempts) == 1
    assert attempts[0].channel == "phone"
    assert attempts[0].outcome == "left voicemail"


def test_status_change_and_manual_attempt_share_one_stream(
    store_factory: Callable[[int], LeadStore],
) -> None:
    store = store_factory(1)
    store.upsert(CID, status="researching")  # auto-logs a status row
    store.append_attempt(CID, channel="mail", outcome="sent")
    channels = {a.channel for a in store_factory(1).list_attempts(CID)}
    assert channels == {"status", "mail"}
