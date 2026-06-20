"""The context/prompt assembler for "Ask Claude" (PRD #187 / #188).

A pure function: a request payload → the system prompt + the Anthropic
``messages`` list. No I/O, no SDK, no settings — just text in, structured
prompt out — so it is trivially unit-testable and the streaming seam
(``ask_client``) stays a thin wrapper over an already-assembled prompt.

This is the **minimal** form for slice 1 (the walking skeleton, #188): a
baked-in domain system prompt describing the catalog, plus the user's
question as the only message. The richer grounding the parent PRD describes
(selection emphasis, on-screen signal records, page text, prior turns) layers
onto this same seam in later slices without changing its shape.
"""

from __future__ import annotations

from dataclasses import dataclass

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

When asked why a signal is rated the way it is, explain it in terms of these \
tags. If you are not sure of a specific fact, say so plainly rather than \
guessing. You explain only — you never take actions or change any data."""


@dataclass(frozen=True)
class AssembledPrompt:
    """The product of the assembler: a system prompt and the ordered Anthropic
    ``messages`` (role/content dicts). Handed verbatim to the streaming client."""

    system: str
    messages: list[dict[str, str]]


def build_prompt(question: str) -> AssembledPrompt:
    """Assemble the minimal prompt for a free-typed question (#188).

    System prompt = the baked-in domain context; messages = the user's
    question as the single turn. Later slices extend ``messages`` with prior
    turns and fold selection/page/signal grounding into the user content,
    reusing this same seam.
    """
    return AssembledPrompt(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
