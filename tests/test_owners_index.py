"""CrossStateOwnerResolver — cross-state Lead identity + rollups (ADR-061/056).

Asserts external behavior on synthetic owner/parcel rows: a national owner
resolves to one stable ``display_cluster_id``; rollups (states, counts,
assessed, score) are correct; conservative exact-name matching does not
over-merge distinct owners. No real parcel-owner names (TESTING.md §4).
"""

from __future__ import annotations

import hashlib
import json
import math

import pandas as pd
import pytest
from preprocess.owners_index import (
    CrossStateOwnerResolver,
    build_owners_index,
    display_cluster_id,
)

# Resolve FIPS → abbr without depending on the geographies table.
ABBR = {"05": "AR", "12": "FL", "30": "MT", "54": "WV"}


def _parcel(
    owner_name,
    state_fips,
    *,
    score,
    assessed=0.0,
    towers=1,
    solar=0,
    kind="corporation",
    tier="",
    oz=False,
    qct=False,
    poverty=False,
):
    return {
        "owner_name": owner_name,
        "owner_kind": kind,
        "state_fips": state_fips,
        "assessed_value": assessed,
        "tower_count": towers,
        "solar_count": solar,
        "has_tower": towers > 0,
        "has_solar": solar > 0,
        "interestingness_score": score,
        "distress_tier": tier,
        "in_oz": oz,
        "in_qct": qct,
        "persistent_poverty": poverty,
    }


def _resolve(rows):
    return CrossStateOwnerResolver(fips_to_abbr=ABBR).resolve(pd.DataFrame(rows))


def _row_for(index_df, owner_norm):
    cid = display_cluster_id(owner_norm)
    matches = index_df[index_df.display_cluster_id == cid]
    assert len(matches) == 1, f"expected exactly one cluster for {owner_norm!r}"
    return matches.iloc[0]


def test_national_owner_resolves_to_one_cluster_across_states():
    # Same owner, two anchor states, *different* mailing situations implied
    # — name-anchored merge must collapse them to ONE Lead.
    idx = _resolve(
        [
            _parcel("WEYERHAEUSER CO", "05", score=0.9, towers=2, assessed=100.0),
            _parcel("WEYERHAEUSER CO", "54", score=0.8, towers=3, assessed=50.0),
        ]
    )
    row = _row_for(idx, "WEYERHAEUSER")
    assert row.states == ["AR", "WV"]
    assert row.n_states == 2
    assert bool(row.cross_state) is True


def test_score_rollup_is_max_plus_alpha_log_count():
    idx = _resolve(
        [
            _parcel("ACME TOWERS LLC", "05", score=0.9),
            _parcel("ACME TOWERS LLC", "54", score=0.7),
        ]
    )
    row = _row_for(idx, "ACME TOWERS")
    expected = round(0.9 + 0.1 * math.log(2), 4)  # max(parcel_scores) + 0.1·ln(n)
    assert row.score == expected
    assert row.max_parcel_score == 0.9


def test_single_parcel_score_has_no_portfolio_bonus():
    # ln(1) == 0, so a one-parcel owner's score is just its parcel score.
    idx = _resolve([_parcel("LONE PINE TRUST", "30", score=0.55)])
    row = _row_for(idx, "LONE PINE")  # TRUST stripped by the normalizer
    assert row.score == 0.55
    assert bool(row.cross_state) is False
    assert row.states == ["MT"]


def test_rollups_sum_counts_and_value():
    idx = _resolve(
        [
            _parcel("BIG SKY HOLDINGS LLC", "30", score=0.6, towers=2, solar=1, assessed=1000.0),
            _parcel("BIG SKY HOLDINGS LLC", "30", score=0.4, towers=1, solar=0, assessed=2500.0),
        ]
    )
    row = _row_for(idx, "BIG HOLDINGS SKY")
    assert row.parcel_count == 2
    assert row.tower_count == 3
    assert row.solar_count == 1
    assert row.total_assessed_value == 3500.0


def test_distress_rollup_takes_max_tier_and_any_flags():
    idx = _resolve(
        [
            _parcel("DELTA AG CO", "05", score=0.5, tier="transitional", oz=True, qct=False),
            _parcel("DELTA AG CO", "12", score=0.5, tier="distressed", oz=False, qct=True),
        ]
    )
    row = _row_for(idx, "AG DELTA")
    assert row.distress_tier == "distressed"  # max severity across parcels
    assert bool(row.in_oz) is True
    assert bool(row.in_qct) is True
    assert bool(row.persistent_poverty) is False


def test_conservative_matching_does_not_over_merge_distinct_owners():
    idx = _resolve(
        [
            _parcel("SMITH JOHN", "05", score=0.5, kind="individual"),
            _parcel("SMITH JANE", "54", score=0.5, kind="individual"),
            # Same surname, different mailing — must stay two Leads.
        ]
    )
    assert len(idx) == 2
    assert {display_cluster_id("JOHN SMITH"), display_cluster_id("JANE SMITH")} == set(
        idx.display_cluster_id
    )


def test_suffix_variants_that_normalize_apart_stay_separate():
    # The conservative normalizer strips "CO" but not "COMPANY", so these
    # do NOT merge — it errs toward under-merging, never over-merging.
    idx = _resolve(
        [
            _parcel("WEYERHAEUSER CO", "05", score=0.9),
            _parcel("WEYERHAEUSER COMPANY", "30", score=0.9),
        ]
    )
    assert len(idx) == 2


def test_display_cluster_id_is_stable_sha1_of_normalized_name():
    assert display_cluster_id("WEYERHAEUSER") == hashlib.sha1(b"WEYERHAEUSER").hexdigest()[:12]
    assert display_cluster_id("") == ""


def test_blank_owner_rows_are_dropped():
    idx = _resolve(
        [
            _parcel("", "05", score=0.9),
            _parcel("   ", "54", score=0.9),
            _parcel("REAL OWNER LLC", "05", score=0.9),
        ]
    )
    assert len(idx) == 1
    assert _row_for(idx, "OWNER REAL") is not None


def test_index_is_sorted_by_score_descending():
    idx = _resolve(
        [
            _parcel("LOW SCORE LLC", "05", score=0.3),
            _parcel("HIGH SCORE LLC", "54", score=0.95),
            _parcel("MID SCORE LLC", "12", score=0.6),
        ]
    )
    assert list(idx.score) == sorted(idx.score, reverse=True)


def test_empty_input_yields_empty_index():
    idx = CrossStateOwnerResolver(fips_to_abbr=ABBR).resolve(pd.DataFrame())
    assert idx.empty
    # the column contract still holds for an empty frame
    assert "display_cluster_id" in idx.columns and "score" in idx.columns


def test_build_owners_index_on_missing_root_is_empty(tmp_path):
    out = build_owners_index(composite_root=tmp_path)
    assert out["count"] == 0
    assert out["owners"] == []
    assert out["schema_version"] == 2


# ── holdings + mailing + tallest tower (Slice 3 / #49) ───────────────────────
def _parcel_with_holding(
    owner_name,
    state_fips,
    *,
    score,
    parcel_id,
    towers_asr=(),
    solar_ids=(),
    bbox=None,
    mailing=None,
    county_fips="",
    acreage=0.0,
):
    """A parcel row carrying the holding/mailing columns the v2 index reads."""
    infra = [{"type": "tower", "id": a, "owner": ""} for a in towers_asr] + [
        {"type": "solar", "id": s, "owner": ""} for s in solar_ids
    ]
    row = _parcel(owner_name, state_fips, score=score, towers=len(towers_asr), solar=len(solar_ids))
    row.update(
        parcel_id=parcel_id,
        county_fips=county_fips,
        acreage=acreage,
        land_use_desc="AV",
        geom_bbox=json.dumps(bbox) if bbox else None,
        infrastructure_summary=json.dumps(infra),
        mailing_addr=(mailing or {}).get("addr", ""),
        mailing_city=(mailing or {}).get("city", ""),
        mailing_state=(mailing or {}).get("state", ""),
        mailing_zip=(mailing or {}).get("zip", ""),
    )
    return row


def test_holdings_aggregate_per_parcel_across_states():
    towers = {
        "T1": {
            "height_m": 120.0,
            "lat": 35.0,
            "lon": -90.0,
            "is_active": True,
            "structure_type_desc": "TOWER",
        },
        "T2": {
            "height_m": 80.0,
            "lat": 38.0,
            "lon": -81.0,
            "is_active": False,
            "structure_type_desc": "MAST",
        },
    }
    idx = CrossStateOwnerResolver(fips_to_abbr=ABBR).resolve(
        pd.DataFrame(
            [
                _parcel_with_holding(
                    "AMERICAN TOWERS LLC",
                    "05",
                    score=0.9,
                    parcel_id="P1",
                    towers_asr=("T1",),
                    bbox=[-90.1, 34.9, -90.0, 35.0],
                    county_fips="05123",
                ),
                _parcel_with_holding(
                    "AMERICAN TOWERS LLC",
                    "54",
                    score=0.8,
                    parcel_id="P2",
                    towers_asr=("T2",),
                    solar_ids=("S1",),
                    bbox=[-81.1, 37.9, -81.0, 38.0],
                ),
            ]
        ),
        towers_by_asr=towers,
    )
    row = _row_for(idx, "AMERICAN TOWERS")
    holdings = row.holdings
    assert {h["state"] for h in holdings} == {"AR", "WV"}
    assert {h["parcel_id"] for h in holdings} == {"P1", "P2"}
    # the cross-state tallest tower wins the rollup
    assert row.tallest_tower_height_m == 120.0
    # tower structures are enriched with height + EPSG:4326 coordinates
    ar = next(h for h in holdings if h["state"] == "AR")
    twr = next(s for s in ar["structures"] if s["type"] == "tower")
    assert twr["height_m"] == 120.0 and twr["active"] is True
    # the bbox-centroid point is the mini-map footprint
    assert ar["point"] == [round((-90.1 + -90.0) / 2, 6), round((34.9 + 35.0) / 2, 6)]


def test_mailing_address_is_the_modal_non_junk_address():
    real = {"addr": "10 MAIN ST", "city": "BOSTON", "state": "MA", "zip": "02101"}
    idx = CrossStateOwnerResolver(fips_to_abbr=ABBR).resolve(
        pd.DataFrame(
            [
                _parcel_with_holding("BIG SKY LLC", "30", score=0.6, parcel_id="A", mailing=real),
                _parcel_with_holding("BIG SKY LLC", "30", score=0.5, parcel_id="B", mailing=real),
                # a junk placeholder must never win the mode
                _parcel_with_holding(
                    "BIG SKY LLC",
                    "30",
                    score=0.4,
                    parcel_id="C",
                    mailing={"addr": "0", "city": "", "state": "", "zip": ""},
                ),
            ]
        )
    )
    row = _row_for(idx, "BIG SKY")
    assert row.mailing_address == real


def test_holdings_present_without_a_tower_map_have_null_heights():
    # No towers_by_asr → structures still list their ASR ids, height None.
    idx = CrossStateOwnerResolver(fips_to_abbr=ABBR).resolve(
        pd.DataFrame(
            [
                _parcel_with_holding(
                    "LONE PINE TRUST", "30", score=0.5, parcel_id="P", towers_asr=("X1",)
                )
            ]
        )
    )
    row = _row_for(idx, "LONE PINE")
    twr = row.holdings[0]["structures"][0]
    assert twr["asr"] == "X1" and twr["height_m"] is None
    assert row.tallest_tower_height_m is None


def test_owner_with_no_resolvable_mailing_has_none():
    idx = CrossStateOwnerResolver(fips_to_abbr=ABBR).resolve(
        pd.DataFrame([_parcel_with_holding("ACME LLC", "05", score=0.5, parcel_id="P")])
    )
    assert _row_for(idx, "ACME").mailing_address is None
