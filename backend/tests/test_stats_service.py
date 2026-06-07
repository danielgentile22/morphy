"""StatsService (UI overhaul P3 / #113, ADR-065/D11): funnel, conversion,
reply rate, win rate, volume by channel; date-range filter; member/state
breakdowns; empty-data edges. Pure over fixture lists (no DB)."""

from __future__ import annotations

from datetime import date

from backend.app.stats_service import ActivityRow, LeadRow, StatsService


def _leads() -> list[LeadRow]:
    # 2 researching, 1 contacted, 1 interested, 1 in_business, 1 uninterested.
    return [
        LeadRow("a", ["AR"], "researching"),
        LeadRow("b", ["AR"], "researching"),
        LeadRow("c", ["FL"], "contacted"),
        LeadRow("d", ["AR", "FL"], "interested"),
        LeadRow("e", ["WV"], "in_business"),
        LeadRow("f", ["AR"], "uninterested"),
    ]


def _acts() -> list[ActivityRow]:
    return [
        ActivityRow(date(2026, 6, 1), "phone", "outbound", "c", 1),
        ActivityRow(date(2026, 6, 2), "mail", "outbound", "d", 2),
        ActivityRow(date(2026, 6, 3), "email", "inbound", "c", None),  # c replied
        ActivityRow(date(2026, 6, 4), "status", "outbound", "c", 1),  # not a touch
    ]


def _svc() -> StatsService:
    return StatsService(_leads(), _acts(), member_name_of={1: "Daniel", 2: "Michael"}.get)


def test_funnel_counts_each_status() -> None:
    f = _svc().compute().funnel
    assert f["researching"] == 2 and f["contacted"] == 1 and f["interested"] == 1
    assert f["in_business"] == 1 and f["uninterested"] == 1


def test_conversion_is_stage_to_stage_on_the_linear_ladder() -> None:
    conv = _svc().compute().conversion
    # reached researching = a,b,c,d,e = 5; reached contacted = c,d,e = 3
    assert conv["researching_to_contacted"] == round(3 / 5, 4)
    # reached contacted=3, interested=2 (d,e) → 2/3
    assert conv["contacted_to_interested"] == round(2 / 3, 4)
    assert conv["interested_to_in_business"] == round(1 / 2, 4)


def test_win_rate_is_in_business_over_worked() -> None:
    # worked = researching(2)+contacted(1)+interested(1)+in_business(1)+uninterested(1) = 6
    assert _svc().compute().win_rate == round(1 / 6, 4)


def test_reply_rate_is_replies_over_contacted() -> None:
    # contacted set: c,d,e (status≥contacted) + f (uninterested) = {c,d,e,f}; c replied → 1/4
    assert _svc().compute().reply_rate == round(1 / 4, 4)


def test_volume_by_channel_counts_outbound_touches_only() -> None:
    vol = _svc().compute().volume_by_channel
    assert vol == {"mail": 1, "phone": 1}  # status row excluded; inbound excluded


def test_date_range_narrows_activity() -> None:
    res = _svc().compute(date_from=date(2026, 6, 2), date_to=date(2026, 6, 2))
    assert res.volume_by_channel == {"mail": 1}
    assert res.activity_total == 1


def test_state_breakdown_and_filter() -> None:
    res = _svc().compute()
    assert res.by_state["AR"]["researching"] == 2  # a, b
    assert res.by_state["FL"]["contacted"] == 1  # c
    # filtering to FL keeps only FL leads (c contacted, d interested)
    fl = _svc().compute(state="FL").funnel
    assert fl["contacted"] == 1 and fl["interested"] == 1 and fl["researching"] == 0


def test_state_filter_also_narrows_activity_metrics() -> None:
    # The state filter must scope activity to the state's leads, not just the
    # funnel — else volume/pace/by-member stay tenant-wide (inconsistent numbers).
    # state=AR drops c's rows (c is FL-only); only d's mail touch survives.
    res = _svc().compute(state="AR")
    assert res.volume_by_channel == {"mail": 1}
    assert res.activity_total == 1
    assert res.by_member == {"Michael": 1}


def test_member_breakdown_and_filter() -> None:
    res = _svc().compute()
    assert res.by_member == {"Daniel": 1, "Michael": 1}  # 1 phone, 1 mail
    only = _svc().compute(member=2)
    assert only.volume_by_channel == {"mail": 1}


def test_reply_rate_ignores_member_filter() -> None:
    # reply_rate's denominator is lead-derived (tenant-wide, like funnel/win),
    # so the numerator must ignore the member filter too — filtering by member
    # must not move the rate (else a member-scoped numerator over a tenant-scoped
    # denominator understates it).
    full = _svc().compute().reply_rate
    assert _svc().compute(member=1).reply_rate == full
    assert _svc().compute(member=2).reply_rate == full


def test_reply_rate_outbound_touch_is_decisive_for_contacted() -> None:
    # "contacted" includes a lead with an outbound touch even below the contacted
    # status rank — this exercises the `cid in outbound` branch independently of
    # the status ladder (both leads are 'researching').
    leads = [LeadRow("g", ["AR"], "researching"), LeadRow("h", ["AR"], "researching")]
    acts = [
        ActivityRow(date(2026, 6, 1), "phone", "outbound", "g", 1),  # g touched
        ActivityRow(date(2026, 6, 2), "email", "inbound", "g", 1),  # g replied
        ActivityRow(date(2026, 6, 3), "mail", "outbound", "h", 1),  # h touched, no reply
    ]
    # contacted = {g, h} via the outbound branch; g replied → 1/2. (Drop the
    # outbound clause and contacted is empty → 0.0, so this pins the branch.)
    assert StatsService(leads, acts).compute().reply_rate == round(1 / 2, 4)


def test_empty_data_is_all_zero_no_crash() -> None:
    res = StatsService([], []).compute()
    assert res.win_rate == 0.0 and res.reply_rate == 0.0
    assert res.volume_by_channel == {} and res.by_state == {}
    assert all(v == 0.0 for v in res.conversion.values())
    assert res.activity_total == 0 and res.active_days == 0
