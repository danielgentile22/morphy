"""AntennaStore behavior: per-antenna manual state, archive/recover, isolation."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.app.antenna_store import AntennaStore

ASR = "1234567"


def _store(new_session: Callable[[], Session], tenant_id: int = 1) -> AntennaStore:
    return AntennaStore(new_session(), tenant_id)


def test_unedited_antenna_has_no_row(new_session: Callable[[], Session]) -> None:
    assert _store(new_session).get(ASR) is None
    assert _store(new_session).archived_asrs() == set()


def test_fields_persist_across_sessions(new_session: Callable[[], Session]) -> None:
    _store(new_session).upsert(
        ASR,
        fields={
            "address": "100 Main St, Pulaski Co, AR",
            "owner_name": "Jane Roe",
            "owner_phone": "555-0100",
            "owner_email": "jane@example.com",
            "notes": "found via county GIS",
        },
    )
    row = _store(new_session).get(ASR)  # a fresh store/session — survives a reload
    assert row is not None
    assert row.address == "100 Main St, Pulaski Co, AR"
    assert row.owner_name == "Jane Roe"
    assert row.owner_phone == "555-0100"
    assert row.owner_email == "jane@example.com"
    assert row.notes == "found via county GIS"
    assert row.archived is False  # editing fields doesn't archive


def test_archive_then_recover(new_session: Callable[[], Session]) -> None:
    _store(new_session).upsert(ASR, archived=True)
    assert _store(new_session).archived_asrs() == {ASR}
    # un-archiving removes it from the set (recoverable, not deleted)
    _store(new_session).upsert(ASR, archived=False)
    assert _store(new_session).archived_asrs() == set()
    assert _store(new_session).get(ASR) is not None  # the row (and its fields) remain


def test_partial_update_leaves_other_fields_untouched(
    new_session: Callable[[], Session],
) -> None:
    _store(new_session).upsert(ASR, fields={"address": "1 First St"})
    _store(new_session).upsert(ASR, fields={"owner_name": "Second Owner"})
    row = _store(new_session).get(ASR)
    assert (row.address, row.owner_name) == ("1 First St", "Second Owner")


def test_archiving_does_not_clear_fields(new_session: Callable[[], Session]) -> None:
    _store(new_session).upsert(ASR, fields={"address": "kept"})
    _store(new_session).upsert(ASR, archived=True)  # archived=... only
    row = _store(new_session).get(ASR)
    assert row.archived is True
    assert row.address == "kept"


def test_archived_state_is_tenant_isolated(new_session: Callable[[], Session]) -> None:
    _store(new_session, tenant_id=1).upsert(ASR, archived=True)
    # A different team must not see tenant 1's archive (ADR-055).
    assert _store(new_session, tenant_id=2).archived_asrs() == set()
    assert _store(new_session, tenant_id=2).get(ASR) is None
