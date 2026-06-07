"""Inbound vs outbound activity direction (UI overhaul P2 / #106, ADR-066).

A **reply** is a first-class *inbound* activity event: ``ContactAttempt`` now
carries a ``direction`` (outbound | inbound, default outbound). The Dashboard
attention feed and the auto follow-up rule read inbound events — never an email
provider — so a Gmail integration later just auto-fills the same rows.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db import init_db
from backend.app.lead_store import LeadStore

CID = "abc123def456"


def test_attempt_defaults_to_outbound(store_factory: Callable[[int], LeadStore]) -> None:
    store_factory(1).append_attempt(CID, channel="phone", outcome="left voicemail")
    attempts = store_factory(1).list_attempts(CID)
    assert len(attempts) == 1
    assert attempts[0].direction == "outbound"


def test_inbound_reply_is_recorded_and_queryable(
    store_factory: Callable[[int], LeadStore],
) -> None:
    store = store_factory(1)
    store.append_attempt(CID, channel="phone", outcome="left voicemail")  # outbound
    store.append_attempt(CID, channel="email", outcome="they replied", direction="inbound")

    replies = store_factory(1).list_replies(CID)
    assert len(replies) == 1
    assert replies[0].direction == "inbound"
    assert replies[0].channel == "email"
    # The outbound touch is still in the full stream but not a reply.
    assert len(store_factory(1).list_attempts(CID)) == 2


def test_status_autolog_is_a_distinct_kind_not_a_reply(
    store_factory: Callable[[int], LeadStore],
) -> None:
    """A status change auto-logs a ``channel='status'`` row; that is outbound
    bookkeeping, never an inbound reply (a reply can arrive with no status
    change, e.g. "who is this?")."""
    store = store_factory(1)
    store.upsert(CID, status="researching")  # auto-logs a status row
    status_rows = [a for a in store_factory(1).list_attempts(CID) if a.channel == "status"]
    assert len(status_rows) == 1
    assert status_rows[0].direction == "outbound"
    assert store_factory(1).list_replies(CID) == []


def test_reply_can_be_logged_without_a_status_change(
    store_factory: Callable[[int], LeadStore],
) -> None:
    store = store_factory(1)
    store.append_attempt(CID, channel="email", outcome="who is this?", direction="inbound")
    lead = store_factory(1).get_lead(CID)
    # Logging a reply creates the Lead (at New) but never advances its status.
    assert lead is not None
    assert lead.status == "new"
    assert len(store_factory(1).list_replies(CID)) == 1


def test_replies_are_tenant_scoped(store_factory: Callable[[int], LeadStore]) -> None:
    store_factory(1).append_attempt(CID, channel="email", outcome="hi", direction="inbound")
    assert len(store_factory(1).list_replies(CID)) == 1
    assert store_factory(2).list_replies(CID) == []  # another tenant sees nothing


# ── additive migration: direction back-fills an existing contact_attempt ──────
_LEGACY_ATTEMPT_DDL = """
CREATE TABLE contact_attempt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    display_cluster_id VARCHAR(64) NOT NULL,
    occurred_on DATE NOT NULL,
    channel VARCHAR(32) NOT NULL,
    outcome VARCHAR(64) NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at DATETIME
)
"""


def test_migration_backfills_direction_on_existing_attempts() -> None:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    with eng.begin() as conn:
        conn.execute(text(_LEGACY_ATTEMPT_DDL))
        conn.execute(
            text(
                "INSERT INTO contact_attempt (tenant_id, display_cluster_id, occurred_on, channel) "
                "VALUES (1, 'old1', '2026-01-01', 'phone')"
            )
        )
    assert "direction" not in {c["name"] for c in inspect(eng).get_columns("contact_attempt")}

    init_db(eng)  # create_all is a no-op for the existing table; migration adds the column

    cols = {c["name"] for c in inspect(eng).get_columns("contact_attempt")}
    assert "direction" in cols
    # The pre-existing row defaults to outbound (not a reply).
    rows = LeadStore(Session(bind=eng, future=True), 1).list_attempts("old1")
    assert len(rows) == 1
    assert rows[0].direction == "outbound"
