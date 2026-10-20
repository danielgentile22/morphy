"""Seed the public read-only demo (ADR-077).

    cd backend && python -m app.demo_seed

Creates the demo team and its read-only credential (``DEMO_USERNAME``,
default ``demo``) with a random password printed once and stored nowhere
else, then puts a handful of fictional leads on the demo board over real
government owners from the owners index, so the board and lead pages have
something to show. Safe to re-run: an existing credential is re-flagged
read-only (its password is untouched), and a board that already has leads
is left alone. A missing owners index skips the leads, not the credential.

The seeded notes, activity, and tasks are fictional and carry no personal
data: contact fields stay blank and every note says it is a demo entry.
"""

from __future__ import annotations

import secrets
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import credentials_store
from .auth_service import resolve_principal
from .lead_store import LeadStore
from .owners_index_service import OwnersIndexService
from .task_store import TaskStore

DEMO_TEAM = "demo"

# Government owners only (ADR-078): a fictional outreach story told against a
# person or a private business could read as real contact with them.
_SEEDABLE_KINDS = frozenset({"gov"})


@dataclass(frozen=True)
class DemoAttempt:
    days_ago: int
    channel: str
    outcome: str
    note: str
    direction: str = "outbound"


@dataclass(frozen=True)
class DemoLead:
    """One fictional storyline: the status ladder walked from New, the lead's
    notes, its logged activity, and an optional follow-up task."""

    path: tuple[str, ...]
    notes: str
    attempts: tuple[DemoAttempt, ...] = ()
    task: str | None = None


_DISCLAIMER = "Demo entry, fictional."

STORYLINES: tuple[DemoLead, ...] = (
    DemoLead(
        path=("researching",),
        notes=f"{_DISCLAIMER} Tower parcel looks owner-held. Next step: pull the deed.",
        task="Pull the county deed for the tower parcel (demo task)",
    ),
    DemoLead(
        path=("researching", "contacted"),
        notes=f"{_DISCLAIMER} Intro letter mailed to the registered address.",
        attempts=(DemoAttempt(12, "mail", "sent", f"{_DISCLAIMER} Intro letter."),),
        task="Follow up on the intro letter (demo task)",
    ),
    DemoLead(
        path=("researching", "contacted"),
        notes=f"{_DISCLAIMER} Two touches so far, no answer yet.",
        attempts=(
            DemoAttempt(20, "mail", "sent", f"{_DISCLAIMER} Intro letter."),
            DemoAttempt(6, "phone", "no answer", f"{_DISCLAIMER} Left no message."),
        ),
    ),
    DemoLead(
        path=("researching", "contacted", "interested"),
        notes=f"{_DISCLAIMER} Owner asked for a lease review. Wants numbers first.",
        attempts=(
            DemoAttempt(30, "mail", "sent", f"{_DISCLAIMER} Intro letter."),
            DemoAttempt(
                9, "email", "replied", f"{_DISCLAIMER} Asked what a review costs.", "inbound"
            ),
            DemoAttempt(8, "email", "sent", f"{_DISCLAIMER} Sent the review outline."),
        ),
    ),
    DemoLead(
        path=("researching", "contacted", "uninterested"),
        notes=f"{_DISCLAIMER} Lease was renegotiated last year. Parked for now.",
        attempts=(
            DemoAttempt(40, "mail", "sent", f"{_DISCLAIMER} Intro letter."),
            DemoAttempt(
                25, "phone", "declined", f"{_DISCLAIMER} Not interested this cycle.", "inbound"
            ),
        ),
    ),
    DemoLead(
        path=("researching", "contacted", "interested", "in_business"),
        notes=f"{_DISCLAIMER} Signed on for a lease review.",
        attempts=(
            DemoAttempt(60, "mail", "sent", f"{_DISCLAIMER} Intro letter."),
            DemoAttempt(45, "phone", "call booked", f"{_DISCLAIMER} Intro call.", "inbound"),
            DemoAttempt(14, "in-person", "signed", f"{_DISCLAIMER} Engagement signed."),
        ),
    ),
)


@dataclass(frozen=True)
class SeedResult:
    # Set only when this run created the credential; never persisted anywhere.
    password: str | None
    leads_created: int
    # Why no leads were seeded this run, or None when they were.
    skipped: str | None


def pick_owners(index: OwnersIndexService, n: int) -> list[str]:
    """The top-scoring government owners that hold at least one tower."""
    owners, _ = index.effective(None)
    picked = [
        o["display_cluster_id"]
        for o in owners
        if o.get("owner_kind") in _SEEDABLE_KINDS and o.get("tower_count", 0) > 0
    ]
    return picked[:n]


def seed(
    session: Session, *, username: str, index: OwnersIndexService, today: date | None = None
) -> SeedResult:
    password = _ensure_read_only_credential(session, username)
    principal = resolve_principal(session, username)
    leads = LeadStore(session, principal.tenant_id)
    if leads.list_leads():
        return SeedResult(password, 0, "the demo board already has leads")
    owner_ids = pick_owners(index, len(STORYLINES))
    if not owner_ids:
        return SeedResult(password, 0, f"no seedable owners in {index.index_path}")

    today = today or date.today()
    tasks = TaskStore(session, principal.tenant_id)
    for cluster_id, story in zip(owner_ids, STORYLINES, strict=False):
        for status in story.path:
            leads.upsert(cluster_id, status=status, logged_by_user_id=principal.user_id)
        leads.upsert(cluster_id, notes=story.notes)
        for a in story.attempts:
            leads.append_attempt(
                cluster_id,
                channel=a.channel,
                outcome=a.outcome,
                note=a.note,
                occurred_on=today - timedelta(days=a.days_ago),
                direction=a.direction,
                logged_by_user_id=principal.user_id,
            )
        if story.task:
            tasks.create(
                title=story.task,
                lead_cluster_id=cluster_id,
                due_date=today + timedelta(days=7),
                created_by_user_id=principal.user_id,
                labels=["demo"],
            )
    return SeedResult(password, len(owner_ids), None)


def _ensure_read_only_credential(session: Session, username: str) -> str | None:
    if credentials_store.get(session, username) is not None:
        credentials_store.set_read_only(session, username, True)
        return None
    password = secrets.token_urlsafe(24)
    credentials_store.add(session, username, DEMO_TEAM, password, read_only=True)
    return password


def _main() -> int:  # pragma: no cover - thin CLI shell over seed()
    from .config import settings
    from .db import SessionLocal, init_db

    init_db()
    index = OwnersIndexService(settings.owners_index_path)
    with SessionLocal() as session:
        result = seed(session, username=settings.demo_username, index=index)
    if result.password is not None:
        print(f"created read-only credential '{settings.demo_username}' (team '{DEMO_TEAM}')")
        print(f"password (shown once, not stored anywhere): {result.password}")
    else:
        print(f"credential '{settings.demo_username}' exists; ensured read-only")
    if result.skipped:
        print(f"leads not seeded: {result.skipped}")
    else:
        print(f"seeded {result.leads_created} demo leads")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(_main())
