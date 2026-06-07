"""Activity read model (UI overhaul P3 / #112, ADR-065/D9).

Assembles the tenant's time-ordered activity from ``ContactAttempt`` — the
ONE stream both Dashboard activity lenses read: **History** (chronological
feed) and **Calendar** (the same events on a time-grid, plus task due-dates
overlaid client-side). Pure over the store + name resolvers; filterable by
lead / member / channel / date range.

Internal ``channel='dismiss'`` rows (attention bookkeeping, #111) are excluded
— they're not user-facing activity.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .lead_store import LeadStore

# Channels that are not "activity done" in the History/Calendar sense.
_EXCLUDED_CHANNELS = {"dismiss"}


@dataclass
class ActivityEvent:
    id: int  # ContactAttempt PK — stable key for keyed {#each} rendering
    date: str  # ISO (occurred_on)
    kind: str  # touch | reply | status | flag
    channel: str
    cluster_id: str
    owner_name: str
    logged_by_user_id: int | None
    member_name: str
    summary: str


def _kind(channel: str, direction: str) -> str:
    if channel == "status":
        return "status"
    if channel == "flag":
        return "flag"
    return "reply" if direction == "inbound" else "touch"


class ActivityService:
    def __init__(
        self,
        leads: LeadStore,
        *,
        owner_name_of: Callable[[str], str] | None = None,
        member_name_of: Callable[[int | None], str] | None = None,
    ) -> None:
        self.leads = leads
        self._owner_name_of = owner_name_of or (lambda _cid: "")
        self._member_name_of = member_name_of or (lambda _uid: "")
        # The unfiltered (dismiss-excluded) tenant stream, fetched at most once
        # per request and shared by digest() + the no-filter events() path
        # (PERF-008) — was two independent full scans + filesorts.
        self._stream_cache: list | None = None

    def _stream(self) -> list:
        if self._stream_cache is None:
            self._stream_cache = self.leads.tenant_attempts(
                exclude_channels=tuple(_EXCLUDED_CHANNELS)
            )
        return self._stream_cache

    def events(
        self,
        *,
        lead: str | None = None,
        member: int | None = None,
        channel: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[ActivityEvent]:
        """The activity stream (newest first), narrowed by any subset of
        lead / member / channel / date range.

        Filters are pushed into SQL (PERF-008) so a scoped query is proportional
        to its result; the common unfiltered call reuses the cached tenant
        stream that digest() also reads, so a single request scans once.
        """
        if lead or member is not None or channel or date_from is not None or date_to is not None:
            rows = self.leads.tenant_attempts(
                lead=lead,
                member=member,
                channel=channel,
                date_from=date_from,
                date_to=date_to,
                exclude_channels=tuple(_EXCLUDED_CHANNELS),
            )
        else:
            rows = self._stream()
        return [
            ActivityEvent(
                id=a.id,
                date=a.occurred_on.isoformat(),
                kind=_kind(a.channel, a.direction),
                channel=a.channel,
                cluster_id=a.display_cluster_id,
                owner_name=self._owner_name_of(a.display_cluster_id),
                logged_by_user_id=a.logged_by_user_id,
                member_name=self._member_name_of(a.logged_by_user_id),
                summary=a.outcome,
            )
            for a in rows
        ]

    def digest(self) -> dict[str, str | None]:
        """Compact recent-activity facts for the Calendar digest: the most
        recent outbound touch + inbound reply dates ('last contact 3d ago,
        last reply yesterday'). Always over the unfiltered recent stream."""
        last_contact: str | None = None
        last_reply: str | None = None
        for a in self._stream():  # newest-first, dismiss already excluded
            if a.channel in _EXCLUDED_CHANNELS:
                continue
            if last_reply is None and a.direction == "inbound":
                last_reply = a.occurred_on.isoformat()
            if (
                last_contact is None
                and a.direction == "outbound"
                and a.channel not in ("status", "flag")
            ):
                last_contact = a.occurred_on.isoformat()
            if last_contact and last_reply:
                break
        return {"last_contact_on": last_contact, "last_reply_on": last_reply}
