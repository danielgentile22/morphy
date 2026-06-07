"""Dashboard Attention feed (UI overhaul P2 / #111, ADR-065/D10).

Pure composition over the tenant's activity + tasks: the things that need
action right now =

  - **Unhandled inbound replies** — a reply (``direction='inbound'``) is
    unhandled until there is a *newer* activity row on that Lead (a logged
    touch, a status change, or an explicit dismiss). Derivable from the
    activity stream alone — no new field (D10).
  - **Overdue tasks** — ``due_date`` before today, not done, assigned to *me*
    or unassigned.

The feed's length is the nav badge count; "Notifications" is this same feed
(no separate system). Acting on an item (which appends newer activity) or
dismissing it clears it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .lead_store import LeadStore
from .task_store import DONE_STATUS, TaskStore

# A dismiss is just a newer activity row, so the "newer activity clears it"
# rule subsumes it — no separate dismissal store (D10).
DISMISS_CHANNEL = "dismiss"


@dataclass
class AttentionItem:
    kind: str  # 'reply' | 'overdue_task'
    title: str
    when: str  # reply date or task due date (ISO)
    cluster_id: str = ""
    owner_name: str = ""
    task_id: int | None = None


class AttentionService:
    def __init__(
        self,
        leads: LeadStore,
        tasks: TaskStore,
        *,
        user_id: int,
        today: date,
        owner_name_of: Callable[[str], str] | None = None,
    ) -> None:
        self.leads = leads
        self.tasks = tasks
        self.user_id = user_id
        self.today = today
        self._owner_name_of = owner_name_of or (lambda _cid: "")

    def unhandled_replies(self) -> list[AttentionItem]:
        """Inbound replies with no newer activity on their Lead (D10)."""
        attempts = self.leads.tenant_attempts()  # newest-first
        # The first row per cid (newest-first order) is that Lead's latest
        # activity; the reply is unhandled iff that latest row is itself inbound.
        seen: set[str] = set()
        out: list[AttentionItem] = []
        for a in attempts:
            cid = a.display_cluster_id
            if cid in seen:
                continue
            seen.add(cid)  # only consider each Lead's latest activity row
            if a.direction == "inbound":
                out.append(
                    AttentionItem(
                        kind="reply",
                        title=f"Reply from {self._owner_name_of(cid) or cid}",
                        when=a.occurred_on.isoformat(),
                        cluster_id=cid,
                        owner_name=self._owner_name_of(cid),
                    )
                )
        return out

    def overdue_tasks(self) -> list[AttentionItem]:
        """Tasks past due, not done, assigned to me or unassigned."""
        out: list[AttentionItem] = []
        for t in self.tasks.list():
            if t.status == DONE_STATUS or t.due_date is None or t.due_date >= self.today:
                continue
            if t.assignee_user_id not in (None, self.user_id):
                continue
            out.append(
                AttentionItem(
                    kind="overdue_task",
                    title=t.title,
                    when=t.due_date.isoformat(),
                    task_id=t.id,
                )
            )
        return out

    def items(self) -> list[AttentionItem]:
        """The full feed — replies first (then overdue tasks), each newest-first."""
        return self.unhandled_replies() + self.overdue_tasks()

    def count(self) -> int:
        return len(self.items())

    def dismiss(self, cluster_id: str) -> None:
        """Clear a Lead's unhandled reply by appending a newer activity row
        (a no-op touch with ``channel='dismiss'``)."""
        self.leads.append_attempt(cluster_id, channel=DISMISS_CHANNEL, outcome="dismissed")
