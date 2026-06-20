"""The context/prompt assembler for "Ask Claude" (PRD #187 / #188 / #189).

A pure function: the request's question + page grounding → the system prompt +
the Anthropic ``messages`` list. No I/O, no SDK, no settings — just data in,
structured prompt out — so it is trivially unit-testable and the streaming seam
(``ask_client``) stays a thin wrapper over an already-assembled prompt.

Slice 1 (#188) was the minimal form: a baked-in domain system prompt plus the
user's question as the only message. Slice 2 (#189) folds the page grounding
into the current turn — the route, the highlighted selection (emphasized), a
truncated slice of the visible page text, and the on-screen signal records —
and prepends the prior thread (clamped to the last K turns). A bare question
with no grounding still produces exactly the slice-1 prompt.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# ── functional caps (the assembler is the one place these are enforced) ──────
# Truncate the visible page text to this many characters — the page text is
# context, not the question, so a long page can't blow up the prompt.
MAX_VISIBLE_TEXT_CHARS = 6000
# Include at most this many on-screen signal records (the catalog/Signals views
# can have hundreds on screen; the question is about a handful).
MAX_SIGNALS = 40
# Keep only the last K prior turns so a long follow-up thread stays bounded.
MAX_THREAD_TURNS = 8

# The baked-in domain system prompt. It teaches Claude what the catalog *is* so
# answers are about *our* data — the AR/FL/MT/WV cell-tower-land project — and
# not a generic web answer (PRD user story #4), and what the trust/freshness
# ratings mean so it can explain *why* a row is rated the way it is (#5).
SYSTEM_PROMPT = """\
You are "Ask Claude", a helper embedded in the Data Catalog of a ground-lease \
intelligence product. The catalog documents the data behind the product and \
how much to trust it. Your job is to answer a reader's question about the \
catalog clearly and concisely, in plain language a non-technical co-founder \
can follow. Explain the specific thing they asked about; do not pad.

What the product is:
- It helps landowners renegotiate ground leases for infrastructure on their \
property — primarily cell towers (freestanding towers in this phase).
- The data problem it solves: no single dataset links a tower to its \
landowner, so the catalog constructs that link by joining several sources.

Geographic scope: four states — Arkansas (AR), Florida (FL), Montana (MT), \
and West Virginia (WV).

Source families behind the catalog:
- FCC ASR (Antenna Structure Registration): the federal registry of \
registered antenna structures (towers), keyed by an ASR number.
- State parcel data: county/state land-ownership parcels, used to identify \
the landowner whose parcel a tower sits on.
- Distress overlays: HUD / ARC / USDA datasets flagging economically \
distressed areas, layered on as signal.

How to read the catalog's trust ratings — every data "signal" carries five \
controlled-vocabulary tags plus a verdict:
- confidence (high / medium / low): the overall, scan-first trust rating.
- upstream_origin: how authoritative the source is (e.g. an official \
registry vs. a derived or inferred value).
- freshness_risk: how stale the value may be given how often the source is \
refreshed.
- derivation_risk: how much processing/inference stands between the raw \
source and the value (more derivation = more room for error).
- verifiability: how readily the value can be independently checked.
- verdict: the auditor's plain-language bottom line for that signal.

When the reader's message includes on-screen context — the page they are on, \
text they highlighted, the visible page text, and structured signal records \
(each carrying its five tags + verdict) — ground your answer in those actual \
values. If they highlighted text, answer about that specific thing. Quote the \
real rating from the signal records rather than guessing (e.g. "rated high \
confidence because its upstream_origin is an official filing"). If a fact \
isn't in the context and you are unsure, say so plainly rather than guessing. \
You explain only — you never take actions or change any data."""


@dataclass(frozen=True)
class AskSignal:
    """One on-screen audit signal's trust record (id + five tags + verdict).
    A plain dataclass so the assembler stays free of pydantic/web concerns; the
    route maps the request model onto it."""

    id: str = ""
    confidence: str = ""
    upstream_origin: str = ""
    freshness_risk: str = ""
    derivation_risk: str = ""
    verifiability: str = ""
    verdict: str = ""


@dataclass(frozen=True)
class AssembledPrompt:
    """The product of the assembler: a system prompt and the ordered Anthropic
    ``messages`` (role/content dicts). Handed verbatim to the streaming client."""

    system: str
    messages: list[dict[str, str]]


def _truncate(text: str, limit: int) -> str:
    """Clamp page text to ``limit`` chars, marking where it was cut so Claude
    knows it's seeing only an excerpt."""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " …[truncated]"


def _format_signal(s: AskSignal) -> str:
    """One signal as a single structured line: id + the five tags, then the
    verdict. Missing fields render as ``?`` rather than vanishing, so the shape
    is stable and Claude can tell "unknown" from "not provided"."""
    line = (
        f"- {s.id or '(unnamed)'}: confidence={s.confidence or '?'}, "
        f"upstream_origin={s.upstream_origin or '?'}, "
        f"freshness_risk={s.freshness_risk or '?'}, "
        f"derivation_risk={s.derivation_risk or '?'}, "
        f"verifiability={s.verifiability or '?'}"
    )
    if s.verdict:
        line += f' — verdict: "{s.verdict}"'
    return line


def _compose_user_message(
    question: str,
    *,
    route: str,
    selection: str | None,
    visible_text: str,
    signals: Sequence[AskSignal],
) -> str:
    """Fold the grounding into the current user turn. With no grounding at all
    this returns the bare question verbatim (the slice-1 shape, preserved so a
    free-typed question is never wrapped)."""
    parts: list[str] = []

    if route.strip():
        parts.append(f"The reader is viewing this page of the catalog: {route.strip()}.")

    sel = (selection or "").strip()
    if sel:
        # Emphasize the selection — it is the subject of the question.
        parts.append(
            "The reader highlighted this text and is asking about it — treat it "
            f"as the subject of the question:\n>>> {sel} <<<"
        )

    capped = list(signals)[:MAX_SIGNALS]
    if capped:
        lines = [_format_signal(s) for s in capped]
        dropped = len(signals) - len(capped)
        if dropped > 0:
            lines.append(f"… and {dropped} more on-screen signal(s) not shown.")
        parts.append(
            "On-screen data signals — ground any claim about a rating in these "
            "actual values, do not invent ratings:\n" + "\n".join(lines)
        )

    page = _truncate(visible_text.strip(), MAX_VISIBLE_TEXT_CHARS)
    if page:
        parts.append("Visible text on the page (context, may be truncated):\n" + page)

    if not parts:
        # No grounding → the question stands alone, byte-for-byte (slice 1).
        return question

    parts.append(f"Question: {question}")
    return "\n\n".join(parts)


def build_prompt(
    question: str,
    *,
    route: str = "",
    selection: str | None = None,
    visible_text: str = "",
    signals: Sequence[AskSignal] = (),
    thread: Sequence[Mapping[str, str]] = (),
) -> AssembledPrompt:
    """Assemble the prompt for one question, optionally grounded in the page.

    The prior ``thread`` (clamped to the last :data:`MAX_THREAD_TURNS` turns) is
    prepended as conversation history; the current question — with selection,
    page text, and signal records folded in — is the final user turn. Each turn
    carries only its raw text, so grounding is attached once (to the current
    turn) rather than repeated through the history."""
    messages: list[dict[str, str]] = []

    for turn in list(thread)[-MAX_THREAD_TURNS:]:
        role = turn.get("role", "user")
        # Anthropic only accepts user/assistant roles; default anything else to
        # user so a malformed history can't break the request.
        messages.append(
            {
                "role": role if role in ("user", "assistant") else "user",
                "content": str(turn.get("content", "")),
            }
        )

    messages.append(
        {
            "role": "user",
            "content": _compose_user_message(
                question,
                route=route,
                selection=selection,
                visible_text=visible_text,
                signals=signals,
            ),
        }
    )
    return AssembledPrompt(system=SYSTEM_PROMPT, messages=messages)
