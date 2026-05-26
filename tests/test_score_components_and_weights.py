"""Tests for the score_components / score_weights split (ADR-058 seam).

Verifies that:
  - compute_components is pure (no weights leak into the dict).
  - apply_weights with DEFAULT_PROFILE reproduces the legacy hardcoded
    numbers byte-for-byte — the parquet score must not drift after the
    refactor.
  - A custom profile changes the score predictably (the live-tuning use
    case from ADR-058).
  - score_parcel_row remains a working backwards-compat shim.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.preprocess.score import score_parcel_row
from scripts.preprocess.score_components import (
    ScoreComponents,
    compute_components,
)
from scripts.preprocess.score_weights import (
    DEFAULT_PROFILE,
    ScoringProfile,
    apply_weights,
)


def _row(**kw) -> pd.Series:
    base = {
        "has_tower": False,
        "has_solar": False,
        "has_billboard": False,
        "tower_count": 0,
        "solar_count": 0,
        "billboard_count": 0,
        "in_oz": False,
        "in_qct": False,
        "persistent_poverty": False,
        "distress_tier": "",
        "owner_kind": "",
        "owner_cluster_size": 0,
    }
    base.update(kw)
    return pd.Series(base)


def test_components_are_weight_free_integers_and_strings():
    c = compute_components(
        _row(has_tower=True, tower_count=3, in_oz=True, owner_kind="LLC")
    )
    assert c.infra_types == 1
    assert c.max_infra_instances == 3
    assert c.overlays == 1
    assert c.owner_kind == "llc"  # lowercased
    # No float weights leaked into the dict:
    d = c.to_dict()
    for k, v in d.items():
        if k in {"arc_tier", "owner_kind"}:
            assert isinstance(v, str)
        else:
            assert isinstance(v, int)


def test_default_profile_reproduces_legacy_scoring():
    # Hand-checked against the original score.py constants — these values
    # must remain stable so the parquet score doesn't drift.
    cases = [
        # (row, expected_score, expected_breakdown subset)
        (
            _row(has_tower=True, tower_count=1),
            0.30,
            {"infrastructure": 0.30},
        ),
        (
            _row(has_tower=True, has_solar=True, tower_count=2, solar_count=3),
            0.40,  # 0.30 + 0.05 (multi type) + 0.05 (multi instance)
            {"infrastructure": 0.40},
        ),
        (
            _row(in_oz=True, in_qct=True, persistent_poverty=True),
            0.25,  # 0.15 + 0.05 * (3-1)
            {"distress_overlays": 0.25},
        ),
        (
            _row(distress_tier="distressed"),
            0.15,
            {"county_tier": 0.15},
        ),
        (
            _row(owner_kind="trust"),
            0.10,
            {"owner_kind": 0.10},
        ),
        (
            _row(owner_cluster_size=8),
            0.10,  # 0.05 + 0.05 (portfolio)
            {"owner_cluster": 0.10},
        ),
    ]
    for row, expected_score, expected_subset in cases:
        score, breakdown = apply_weights(compute_components(row), DEFAULT_PROFILE)
        assert score == pytest.approx(expected_score)
        for k, v in expected_subset.items():
            assert breakdown[k] == pytest.approx(v)


def test_score_clipped_to_unit_interval():
    # Stack everything to overflow 1.0 — must clip to 1.0
    row = _row(
        has_tower=True,
        has_solar=True,
        has_billboard=True,
        tower_count=5,
        in_oz=True,
        in_qct=True,
        persistent_poverty=True,
        distress_tier="distressed",
        owner_kind="llc",
        owner_cluster_size=20,
    )
    score, _ = apply_weights(compute_components(row), DEFAULT_PROFILE)
    assert 0.0 <= score <= 1.0
    assert score == pytest.approx(1.0)


def test_custom_profile_changes_score():
    """The live-tuning ADR-058 use case: changing weights changes scores."""
    row = _row(in_oz=True, in_qct=True, distress_tier="distressed")
    default_score, _ = apply_weights(compute_components(row), DEFAULT_PROFILE)

    # Co-founder cranks distress weights up 2×
    distress_heavy = ScoringProfile(
        name="distress-first",
        distress_first=0.30,
        distress_extra=0.10,
        arc_tier={"distressed": 0.30, "at-risk": 0.20, "transitional": 0.10},
    )
    boosted, breakdown = apply_weights(compute_components(row), distress_heavy)
    assert boosted > default_score
    assert breakdown["county_tier"] == pytest.approx(0.30)


def test_score_parcel_row_shim_matches_split():
    row = _row(has_tower=True, in_qct=True, distress_tier="at-risk")
    shim_score, shim_breakdown = score_parcel_row(row)
    direct_score, direct_breakdown = apply_weights(
        compute_components(row), DEFAULT_PROFILE
    )
    assert shim_score == direct_score
    assert shim_breakdown == direct_breakdown


def test_components_handle_missing_columns():
    # Early-pipeline row — only some columns exist.
    sparse = pd.Series({"has_tower": True})
    c = compute_components(sparse)
    assert c.infra_types == 1
    assert c.overlays == 0
    assert c.arc_tier == ""


def test_components_dataclass_default_construction():
    # Used by tests / code that builds components synthetically rather
    # than from a row.
    c = ScoreComponents()
    score, _ = apply_weights(c, DEFAULT_PROFILE)
    assert score == 0.0
