"""Lead status state machine (ADR-061 / CONTEXT.md).

Single status per Lead. The ladder branches after Contacted:

    New ──▶ Researching ──▶ Contacted ──┬──▶ Interested ──▶ In Business
                                        └──▶ Uninterested   (terminal)

Default = New. ``in_business`` is the won terminal; ``uninterested`` the
lost terminal. ``in_business`` is reachable only via ``interested``.
Re-saving the same status is always allowed (saving a note without
advancing). This mirrors ``app/src/lib/lead-status.ts`` (the Vitest
parity target); keep the two in lockstep.
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
TERMINAL_STATUSES: frozenset[str] = frozenset({"in_business", "uninterested"})

# Allowed *forward* transitions (identity is handled separately). Strict
# one-rung steps plus the documented "give up → uninterested" branch from
# any worked-but-not-closed state.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "new": frozenset({"researching"}),
    "researching": frozenset({"contacted", "uninterested"}),
    "contacted": frozenset({"interested", "uninterested"}),
    "interested": frozenset({"in_business", "uninterested"}),
    "in_business": frozenset(),
    "uninterested": frozenset(),
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


def next_statuses(frm: str) -> list[str]:
    """Statuses selectable from ``frm`` (itself + legal next), in ladder order."""
    if not is_valid_status(frm):
        return []
    allowed = {frm} | set(ALLOWED_TRANSITIONS.get(frm, frozenset()))
    return [s for s in STATUSES if s in allowed]


def validate_transition(frm: str, to: str) -> None:
    """Raise ``InvalidTransition`` if ``frm → to`` is not allowed."""
    if not is_valid_status(to):
        raise InvalidTransition(f"unknown status {to!r}")
    if not can_transition(frm, to):
        raise InvalidTransition(f"illegal transition {frm} → {to}")
