"""Outreach analytics (UI overhaul P3 / #113, ADR-065/D11).

Pure over the owner population (cid · states · status) + the activity stream —
no new write data. Computes the funnel, stage conversion, reply rate, win rate,
outreach volume by channel, and activity pace; filterable by date range and
broken down by team member + state.

All inputs are plain lists so the whole thing is unit-testable without a DB;
the route assembles them from the owners index + LeadStore.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

# The linear progression ladder (the Uninterested branch is terminal/off-line).
_LADDER = ["new", "researching", "contacted", "interested", "in_business"]
_RANK = {s: i for i, s in enumerate(_LADDER)}
_WORKED = {"researching", "contacted", "interested", "in_business", "uninterested"}
# Channels that aren't outreach "touches" (volume/reply metrics ignore them).
_NON_TOUCH = {"status", "flag", "dismiss"}


@dataclass
class LeadRow:
    cid: str
    states: list[str]
    status: str


@dataclass
class ActivityRow:
    occurred_on: date
    channel: str
    direction: str
    cid: str
    logged_by_user_id: int | None = None


@dataclass
class StatsResult:
    funnel: dict[str, int]
    conversion: dict[str, float]
    reply_rate: float
    win_rate: float
    volume_by_channel: dict[str, int]
    activity_total: int
    active_days: int
    by_state: dict[str, dict[str, int]] = field(default_factory=dict)
    by_member: dict[str, int] = field(default_factory=dict)


class StatsService:
    def __init__(
        self,
        leads: list[LeadRow],
        attempts: list[ActivityRow],
        *,
        member_name_of=None,
    ) -> None:
        self.leads = leads
        self.attempts = attempts
        self._member_name_of = member_name_of or (lambda uid: str(uid))

    def compute(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        state: str | None = None,
        member: int | None = None,
    ) -> StatsResult:
        leads = [lead for lead in self.leads if state is None or state in lead.states]
        # Activity carries no state of its own, so scope it to the state-filtered
        # lead population (cid space is shared) — otherwise volume/pace/by-member
        # stay tenant-wide while the funnel narrows, showing inconsistent numbers
        # on one screen.
        state_cids = {lead.cid for lead in leads}

        def in_window(a: ActivityRow) -> bool:
            return (
                (date_from is None or a.occurred_on >= date_from)
                and (date_to is None or a.occurred_on <= date_to)
                and (state is None or a.cid in state_cids)
            )

        acts = [
            a
            for a in self.attempts
            if in_window(a) and (member is None or a.logged_by_user_id == member)
        ]
        # reply_rate's denominator is lead-derived (tenant-wide, like funnel/
        # conversion/win_rate), so its numerator must ignore the member filter
        # too — else a member-scoped numerator sits over a tenant-scoped
        # denominator and understates the rate.
        reply_acts = [a for a in self.attempts if in_window(a)]

        funnel = self._funnel(leads)
        return StatsResult(
            funnel=funnel,
            conversion=self._conversion(funnel),
            reply_rate=self._reply_rate(leads, reply_acts),
            win_rate=self._win_rate(funnel),
            volume_by_channel=self._volume_by_channel(acts),
            activity_total=len(acts),
            active_days=len({a.occurred_on for a in acts}),
            by_state=self._by_state(leads),
            by_member=self._by_member(acts),
        )

    # ── metric helpers ────────────────────────────────────────────────────────
    def _funnel(self, leads: list[LeadRow]) -> dict[str, int]:
        c = Counter(lead.status for lead in leads)
        order = [*_LADDER, "uninterested"]
        return {s: int(c.get(s, 0)) for s in order}

    def _conversion(self, funnel: dict[str, int]) -> dict[str, float]:
        """Stage-to-stage rate on the linear ladder: of leads that reached
        stage N, the share that reached N+1. 'reached X' = current rank ≥ X
        (Uninterested excluded — it's an off-ladder terminal)."""
        reached = {s: sum(funnel[t] for t in _LADDER if _RANK[t] >= _RANK[s]) for s in _LADDER}
        out: dict[str, float] = {}
        for a, b in zip(_LADDER, _LADDER[1:], strict=False):
            out[f"{a}_to_{b}"] = round(reached[b] / reached[a], 4) if reached[a] else 0.0
        return out

    def _reply_rate(self, leads: list[LeadRow], acts: list[ActivityRow]) -> float:
        """Of contacted leads (status ≥ contacted OR an outbound touch), the
        share with an inbound reply."""
        cids = {lead.cid for lead in leads}
        outbound = {
            a.cid for a in acts if a.direction == "outbound" and a.channel not in _NON_TOUCH
        }
        replied = {a.cid for a in acts if a.direction == "inbound"}
        contacted = {
            lead.cid
            for lead in leads
            if _RANK.get(lead.status, -1) >= _RANK["contacted"]
            or lead.status == "uninterested"
            or lead.cid in outbound
        }
        contacted &= cids
        if not contacted:
            return 0.0
        return round(len(replied & contacted) / len(contacted), 4)

    def _win_rate(self, funnel: dict[str, int]) -> float:
        worked = sum(funnel[s] for s in funnel if s in _WORKED)
        return round(funnel["in_business"] / worked, 4) if worked else 0.0

    def _volume_by_channel(self, acts: list[ActivityRow]) -> dict[str, int]:
        c = Counter(
            a.channel for a in acts if a.direction == "outbound" and a.channel not in _NON_TOUCH
        )
        return dict(sorted(c.items()))

    def _by_state(self, leads: list[LeadRow]) -> dict[str, dict[str, int]]:
        states: dict[str, Counter] = {}
        for lead in leads:
            for st in lead.states:
                states.setdefault(st, Counter())[lead.status] += 1
        order = [*_LADDER, "uninterested"]
        return {st: {s: int(c.get(s, 0)) for s in order} for st, c in sorted(states.items())}

    def _by_member(self, acts: list[ActivityRow]) -> dict[str, int]:
        c: Counter[str] = Counter()
        for a in acts:
            if a.direction == "outbound" and a.channel not in _NON_TOUCH:
                c[self._member_name_of(a.logged_by_user_id)] += 1
        return dict(sorted(c.items()))
