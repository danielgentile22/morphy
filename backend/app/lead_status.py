"""Lead status state machine (ADR-061 / CONTEXT.md).

Single status per Lead. The ladder branches after Contacted:

    New ──▶ Researching ──▶ Contacted ──┬──▶ Interested ──▶ In Business
                                        └──▶ Uninterested   (reopenable)

Default = New. ``in_business`` is the one true terminal (won) — reachable
only via ``interested``, with no way out. ``uninterested`` (lost/parked) is
closed-but-reopenable: it can move back to ANY status so a mis-classified
lead is never stranded. Re-saving the same status is always allowed (saving
a note without advancing). This mirrors ``app/src/lib/lead-status.ts`` (the
Vitest parity target); keep the two in lockstep.
"""

from __future__ import annotations

STATUSES: tuple[str, ...] = (
    "new",
    "researching",
    "contacted",
    "interested",
    "in_business",
    "uninterested",
)

INITIAL_STATUS = "new"
# Closed/end-of-pipeline lanes (kanban "closed" visual treatment), NOT a
# transition-lock: ``uninterested`` shows as closed but is reopenable; only
# ``in_business`` is truly locked.
TERMINAL_STATUSES: frozenset[str] = frozenset({"in_business", "uninterested"})

# Allowed *forward* transitions (identity is handled separately). Strict
# one-rung steps plus the documented "give up → uninterested" branch from
# any worked-but-not-closed state. ``uninterested`` is the exception: a
# lost/parked lead can be reopened to ANY status, so a mis-click is never a
# dead end. ``in_business`` stays a true terminal (won — no outgoing moves).
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "new": frozenset({"researching"}),
    "researching": frozenset({"contacted", "uninterested"}),
    "contacted": frozenset({"interested", "uninterested"}),
    "interested": frozenset({"in_business", "uninterested"}),
    "in_business": frozenset(),
    "uninterested": frozenset({"new", "researching", "contacted", "interested", "in_business"}),
}


class InvalidTransition(ValueError):
    """Raised when a status change violates the ladder."""


def is_valid_status(status: str) -> bool:
    return status in STATUSES


def can_transition(frm: str, to: str) -> bool:
    """True if ``frm → to`` is legal. Same-status (idempotent save) is legal."""
    if not is_valid_status(frm) or not is_valid_status(to):
        return False
    if frm == to:
        return True
    return to in ALLOWED_TRANSITIONS.get(frm, frozenset())


def validate_transition(frm: str, to: str) -> None:
    """Raise ``InvalidTransition`` if ``frm → to`` is not allowed."""
    if not is_valid_status(to):
        raise InvalidTransition(f"unknown status {to!r}")
    if not can_transition(frm, to):
        raise InvalidTransition(f"illegal transition {frm} → {to}")
