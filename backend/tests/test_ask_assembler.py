"""The "Ask Claude" prompt assembler (PRD #188).

Pure-function tests over external behavior: given a question, what does the
assembled prompt contain? No I/O, no SDK.
"""

from __future__ import annotations

from backend.app.ask_assembler import build_prompt


def test_system_prompt_is_present_and_domain_grounded() -> None:
    prompt = build_prompt("anything")
    assert prompt.system.strip(), "the baked-in system prompt must be present"
    # It grounds Claude in *our* project, not a generic answer: the four-state
    # scope and the source families a reader will ask about.
    for token in ("Arkansas", "Florida", "Montana", "West Virginia", "FCC ASR", "parcel"):
        assert token in prompt.system


def test_system_prompt_explains_the_trust_ratings() -> None:
    # So Claude can explain *why* a signal is rated the way it is (PRD story #5).
    prompt = build_prompt("why is this medium confidence?")
    for tag in (
        "confidence",
        "upstream_origin",
        "freshness_risk",
        "derivation_risk",
        "verifiability",
        "verdict",
    ):
        assert tag in prompt.system


def test_question_is_the_single_user_message() -> None:
    prompt = build_prompt("What is an FCC ASR registration?")
    assert prompt.messages == [
        {"role": "user", "content": "What is an FCC ASR registration?"}
    ]


def test_question_is_passed_through_verbatim() -> None:
    # The assembler never mutates the user's wording.
    q = "  ok, but why does that matter for a deal?  "
    assert build_prompt(q).messages[0]["content"] == q
