"""Cross-language contract: the Lead status ladder, Python side (PRD #137).

Asserts ``backend/app/lead_status.py`` against ``contracts/lead_status_ladder.json``
— the same language-neutral fixture the frontend's Vitest suite asserts
``app/src/lib/lead-status.ts`` against (``app/tests/unit/contract-lead-status.test.ts``).
If the ladder drifts on one side, that side's suite goes red against this fixture.
The fixture is the contract; editing it is editing the contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app import lead_status

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts" / "lead_status_ladder.json").read_text()
)


def test_status_set_matches_contract() -> None:
    assert list(lead_status.STATUSES) == CONTRACT["statuses"]
    assert lead_status.INITIAL_STATUS == CONTRACT["initial_status"]
    assert set(lead_status.TERMINAL_STATUSES) == set(CONTRACT["terminal_statuses"])


def test_allowed_transitions_table_matches_contract() -> None:
    table = {frm: sorted(tos) for frm, tos in lead_status.ALLOWED_TRANSITIONS.items()}
    expected = {frm: sorted(tos) for frm, tos in CONTRACT["allowed_transitions"].items()}
    assert table == expected


@pytest.mark.parametrize(
    "case", CONTRACT["transition_cases"], ids=lambda c: f"{c['from']}->{c['to']}"
)
def test_can_transition_matches_contract(case: dict) -> None:
    assert lead_status.can_transition(case["from"], case["to"]) is case["allowed"]


@pytest.mark.parametrize(
    "case", CONTRACT["transition_cases"], ids=lambda c: f"{c['from']}->{c['to']}"
)
def test_validate_transition_matches_contract(case: dict) -> None:
    if case["allowed"]:
        lead_status.validate_transition(case["from"], case["to"])  # must not raise
    else:
        with pytest.raises(lead_status.InvalidTransition):
            lead_status.validate_transition(case["from"], case["to"])
