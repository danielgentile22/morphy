"""The "Ask Claude" prompt assembler (PRD #188 / grounding #189).

Pure-function tests over external behavior: given a question (and, for slice 2,
the page grounding), what does the assembled prompt contain? No I/O, no SDK.
"""

from __future__ import annotations

from backend.app.ask_assembler import (
    MAX_SIGNALS,
    MAX_THREAD_TURNS,
    MAX_VISIBLE_TEXT_CHARS,
    AskSignal,
    build_prompt,
)


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


def test_bare_question_is_unwrapped_when_there_is_no_grounding() -> None:
    # Slice-1 shape preserved: with no page context the question stands alone.
    assert build_prompt("hi").messages == [{"role": "user", "content": "hi"}]


# ── slice 2: grounding (#189) ────────────────────────────────────────────────
def _user(prompt) -> str:
    return prompt.messages[-1]["content"]


def test_route_orients_the_answer() -> None:
    content = _user(build_prompt("what is this?", route="Signal: owner_name@12"))
    assert "owner_name@12" in content
    assert content.endswith("Question: what is this?")


def test_selection_is_emphasized_as_the_subject() -> None:
    content = _user(build_prompt("explain", selection="owner_name field"))
    assert "owner_name field" in content
    assert "highlighted" in content.lower()
    assert ">>>" in content  # the selection is marked off, not buried in prose
    assert content.endswith("Question: explain")


def test_signals_appear_as_structured_context() -> None:
    sig = AskSignal(
        id="owner_name@12",
        confidence="high",
        upstream_origin="official_filing",
        freshness_risk="low",
        derivation_risk="low",
        verifiability="high",
        verdict="Authoritative public registry.",
    )
    content = _user(build_prompt("why high?", signals=[sig]))
    assert "owner_name@12" in content
    assert "confidence=high" in content
    assert "upstream_origin=official_filing" in content
    assert "Authoritative public registry." in content


def test_page_text_is_truncated_to_the_cap() -> None:
    long = "lorem ipsum " * 5000  # far over MAX_VISIBLE_TEXT_CHARS
    content = _user(build_prompt("summarize", visible_text=long))
    assert "[truncated]" in content
    assert long not in content  # the full page text is not embedded
    # Only a bounded slice rides along (plus the framing + question).
    assert len(content) < len(long)


def test_signal_count_is_capped() -> None:
    sigs = [AskSignal(id=f"s{i}") for i in range(MAX_SIGNALS + 5)]
    content = _user(build_prompt("q", signals=sigs))
    assert f"- s{MAX_SIGNALS - 1}:" in content  # last kept signal
    assert f"- s{MAX_SIGNALS}:" not in content  # first dropped signal
    assert "more on-screen signal" in content  # the drop is disclosed


def test_thread_is_clamped_to_the_last_k_turns() -> None:
    thread = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"t{i}"}
        for i in range(MAX_THREAD_TURNS * 2)
    ]
    prompt = build_prompt("now", thread=thread)
    # The last K prior turns, then the current question as the final turn.
    assert len(prompt.messages) == MAX_THREAD_TURNS + 1
    history = prompt.messages[:-1]
    assert [m["content"] for m in history] == [t["content"] for t in thread[-MAX_THREAD_TURNS:]]
    assert prompt.messages[-1] == {"role": "user", "content": "now"}


def test_unknown_thread_role_defaults_to_user() -> None:
    # A malformed history can't break the request (Anthropic only takes
    # user/assistant).
    prompt = build_prompt("q", thread=[{"role": "system", "content": "x"}])
    assert prompt.messages[0]["role"] == "user"


def test_grounding_pieces_compose_with_the_question_last() -> None:
    sig = AskSignal(id="owner_name@12", confidence="medium")
    content = _user(
        build_prompt(
            "why medium?",
            route="Signals browser",
            selection="medium",
            visible_text="a small page",
            signals=[sig],
        )
    )
    # Route, selection, signals, and page text all present; question comes last.
    assert "Signals browser" in content
    assert "owner_name@12" in content
    assert "a small page" in content
    assert content.rstrip().endswith("Question: why medium?")
