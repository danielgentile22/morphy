"""AskLogStore behavior (PRD #187 / slice 3 / #190): record + read-back, the
context snapshot, and tenant isolation — the multi-tenant chokepoint.

Pure store tests over the ``engine`` fixture (``create_all`` schema); the
migration that builds the same table in production is proven equivalent in
``test_migration.py``."""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.ask_log_store import AskLogStore, split_signal_ids


def _store(engine: Engine, tenant_id: int) -> AskLogStore:
    return AskLogStore(Session(bind=engine, future=True), tenant_id)


def test_record_round_trips_on_read_back(engine: Engine) -> None:
    row = _store(engine, 1).record(
        username="dev",
        question="What is an FCC ASR registration?",
        answer="It is the FCC's antenna-structure registry.",
        model="claude-sonnet-4-6",
    )
    assert row.id is not None
    fetched = _store(engine, 1).get(row.id)
    assert fetched is not None
    assert fetched.question == "What is an FCC ASR registration?"
    assert fetched.answer == "It is the FCC's antenna-structure registry."
    assert fetched.username == "dev"
    assert fetched.model == "claude-sonnet-4-6"


def test_context_snapshot_persists(engine: Engine) -> None:
    # The whole point of the slice: capture *what was on screen* so a future
    # review can mine it — route, selection, and the on-screen signal ids.
    row = _store(engine, 1).record(
        username="dev",
        question="why high?",
        answer="Because it's an official filing.",
        route="Signal: owner_name@12",
        selection="owner_name",
        signal_ids=["owner_name@12", "foo@05"],
        model="claude-sonnet-4-6",
        input_tokens=120,
        output_tokens=42,
    )
    fetched = _store(engine, 1).get(row.id)
    assert fetched is not None
    assert fetched.route == "Signal: owner_name@12"
    assert fetched.selection == "owner_name"
    assert split_signal_ids(fetched.signal_ids) == ["owner_name@12", "foo@05"]
    assert (fetched.input_tokens, fetched.output_tokens) == (120, 42)


def test_no_selection_and_no_signals_store_as_empty(engine: Engine) -> None:
    # A free-typed question with nothing on screen — a question-only snapshot.
    row = _store(engine, 1).record(username="dev", question="q", answer="a")
    fetched = _store(engine, 1).get(row.id)
    assert fetched is not None
    assert fetched.selection is None
    assert fetched.signal_ids == ""
    assert fetched.route == ""


def test_list_returns_this_tenants_qa_newest_first(engine: Engine) -> None:
    store = _store(engine, 1)
    store.record(username="dev", question="first", answer="a1")
    store.record(username="dev", question="second", answer="a2")
    questions = [r.question for r in _store(engine, 1).list()]
    assert questions == ["second", "first"]  # newest first


def test_one_tenant_can_never_read_anothers_qa(engine: Engine) -> None:
    mine = _store(engine, 1).record(username="dev", question="mine", answer="a")
    # Tenant 2 cannot see tenant 1's row by id, nor in its list.
    assert _store(engine, 2).get(mine.id) is None
    _store(engine, 2).record(username="other", question="theirs", answer="b")
    assert [r.question for r in _store(engine, 1).list()] == ["mine"]
    assert [r.question for r in _store(engine, 2).list()] == ["theirs"]


def test_signal_ids_are_normalized(engine: Engine) -> None:
    # Blanks dropped, whitespace trimmed, order preserved (join_signal_ids).
    row = _store(engine, 1).record(
        username="dev",
        question="q",
        answer="a",
        signal_ids=[" a@12 ", "", "b@05"],
    )
    fetched = _store(engine, 1).get(row.id)
    assert fetched is not None
    assert fetched.signal_ids == "a@12,b@05"
