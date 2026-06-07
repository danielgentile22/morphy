"""Auto follow-ups: schedule-forward, cancel-on-reply (UI overhaul P5 / #116,
ADR-066 / D12).

No background scheduler. The first outbound touch (or status → Contacted)
eagerly creates a ``source='auto'`` follow-up Task due at ``anchor + window``;
an inbound reply before then cancels it. The auto-task is a normal editable
Task (reassign / snooze / label), so it flows into the unified Tasks list,
Calendar, and Attention feed like any other.

One rule, on/off + window in settings; architected so more rules slot in
without a full engine.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from .lead_store import LeadStore
from .models import Task
from .settings_store import SettingsStore
from .task_store import DONE_STATUS, TaskStore

# Lead is still "awaiting" a reply at these statuses (D12). Interested / In
# Business / Uninterested are resolved — no chase.
_AWAITING = {"new", "researching", "contacted"}


class AutoFollowUpRule:
    def __init__(
        self,
        leads: LeadStore,
        tasks: TaskStore,
        settings: SettingsStore,
        *,
        owner_name_of: Callable[[str], str] | None = None,
    ) -> None:
        self.leads = leads
        self.tasks = tasks
        self.settings = settings
        self._owner_name_of = owner_name_of or (lambda _cid: "")

    def maybe_schedule(self, cid: str, *, anchor: date, status: str) -> Task | None:
        """Schedule a follow-up if eligible (rule on, lead awaiting, no reply
        since the anchor, none already open). Idempotent — at most one open
        auto follow-up per lead. Returns the created task, or None."""
        if not self.settings.auto_followup_enabled:
            return None
        if status not in _AWAITING:
            return None
        if self._has_open_auto(cid):
            return None
        if self._has_reply_since(cid, anchor):
            return None
        window = self.settings.auto_followup_window_days
        name = self._owner_name_of(cid) or cid
        return self.tasks.create(
            title=f"Follow up: {name}",
            description="Auto-scheduled — no reply since first contact.",
            priority="med",
            due_date=anchor + timedelta(days=window),
            lead_cluster_id=cid,
            source="auto",
        )

    def cancel_on_reply(self, cid: str) -> int:
        """An inbound reply cancels the lead's open auto follow-up(s). Returns
        how many were cancelled (deleted)."""
        cancelled = 0
        for t in self.tasks.list_filtered(lead_cluster_id=cid, source="auto"):
            if t.status != DONE_STATUS:
                self.tasks.delete(t.id)
                cancelled += 1
        return cancelled

    # ── helpers ───────────────────────────────────────────────────────────────
    def _has_open_auto(self, cid: str) -> bool:
        return any(
            t.status != DONE_STATUS
            for t in self.tasks.list_filtered(lead_cluster_id=cid, source="auto")
        )

    def _has_reply_since(self, cid: str, anchor: date) -> bool:
        return any(r.occurred_on >= anchor for r in self.leads.list_replies(cid))
