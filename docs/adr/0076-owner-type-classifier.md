# ADR-076: Owner-type classifier — expanded regex first, LLM for the ambiguous residual

**Status:** Accepted — **stage 1 implemented** (#222): expanded regex + curated towerco list (`towerco`/`utility`/`nonprofit` added, ordered before the generic legal suffixes) + a labeled-sample regression fixture. Stage 3 (LLM residual) stays deferred — evidence-gated on the residual size, per the decision below.
**Date:** 2026-07-03
**Budget posture:** [ADR-057](0057-budget-posture-reframed.md).

## Context

The audit found `owner_kind` is a **name-regex guess**, reliable only for clean legal suffixes and obvious government names. The co-founder's direction this session: get a much better regex down first, then quantify whether an LLM (and paid spend) is worth it.

## Decision — two stages, the second evidence-gated

1. **Expanded regex + curated lists (ship first, no API dependency).** Add patterns for **trust, utility, cooperative, religious/nonprofit, towerco (curated list), broadened government**; curated name lists for entities with no suffix tell (e.g. a towerco with no `LLC`/`INC`). Taxonomy: individual / LLC / corporate / government / trust / utility / towerco / nonprofit / unknown.
2. **Evaluation gate.** Hand-label a **~200-owner sample**; report accuracy **old-regex vs new-regex** on it. The labeled sample doubles as a regression fixture.
3. **LLM for the residual only (deferred, scoped).** The one thing regex can't do reliably — a **bare personal name** (individual vs unregistered sole-proprietor business). Classify **only the ambiguous residual** (~2–3k names), not all ~16k owners, with **Haiku**, batched.
   - **Cost:** classifying *all* ~16k owners once ≈ **under $2** (Haiku, batched, ~3–4M tokens); residual-only is far less. One-time, re-run only when owners change. Well inside ADR-057's posture.
   - **Gate:** only spend it if stage-2's measurement shows the residual is big enough to matter. Fully regex-classifiable owners never touch the API.

## Consequences

- Better `owner_kind` feeds facets/filters and the owner-type signal in scoring ([ADR-073](0073-interestingness-reweight.md)).
- Regex stage ships immediately; the LLM stage is optional, cheap, and evidence-gated.
- Classifier covered by tests (the labeled sample is the fixture). Composite regen when `owner_kind` values change.

## Alternatives considered

- **LLM-classify all ~16k up front** — rejected; pays for the ~80% the expanded regex already nails.
- **Keep the status-quo regex** — rejected; that's the audit finding.
