# ADR-076: Owner-type classifier with expanded regex first and an LLM for the ambiguous residual

**Status:** Accepted. **Stage 1 implemented:** expanded regex plus a curated tower-company list (`towerco`/`utility`/`nonprofit` added, ordered before the generic legal suffixes) plus a labeled-sample regression fixture. Stage 3 (LLM residual) was never built. It was evidence-gated on the residual size, per the decision below.
**Date:** 2026-07-03
**Origin:** one of seven decisions (ADR-070-076) from a data audit, whose working files are not part of this repo.
**Budget posture:** [ADR-057](0057-budget-posture-reframed.md).

## Context

The audit found `owner_kind` is a **name-regex guess**, reliable only for clean legal suffixes and obvious government names. The user's direction: get a much better regex down first, then quantify whether an LLM (and paid spend) is worth it.

## Decision: two stages, the second evidence-gated

1. **Expanded regex plus curated lists (ship first, no API dependency).** Add patterns for **trust, utility, cooperative, religious/nonprofit, tower company (curated list), broadened government**. Add curated name lists for entities with no suffix tell (for example a tower company with no `LLC`/`INC`). Taxonomy: individual / LLC / corporate / government / trust / utility / towerco / nonprofit / unknown.
2. **Evaluation gate.** Hand-label a **~200-owner sample** and report accuracy **old regex vs new regex** on it. The labeled sample doubles as a regression fixture.
3. **LLM for the residual only (deferred, scoped).** This covers the one thing regex can't do reliably: a **bare personal name** (individual vs unregistered sole-proprietor business). Classify **only the ambiguous residual** (~2-3k names), not all ~16k owners, with **Haiku**, batched.
   - **Cost:** classifying *all* ~16k owners once comes to **under $2** (Haiku, batched, ~3-4M tokens); residual-only is far less. It is one-time, re-run only when owners change, and well inside ADR-057's posture.
   - **Gate:** only spend it if stage 2's measurement shows the residual is big enough to matter. Fully regex-classifiable owners never touch the API.

## Consequences

- Better `owner_kind` feeds facets, filters and the owner-type signal in scoring ([ADR-073](0073-interestingness-reweight.md)).
- The regex stage ships immediately; the LLM stage is optional, cheap, and evidence-gated.
- Classifier covered by tests (the labeled sample is the fixture). Composite regen when `owner_kind` values change.

## Alternatives considered

- **LLM-classify all ~16k up front.** Rejected. It pays for the ~80% the expanded regex already gets right.
- **Keep the status-quo regex.** Rejected. That is the audit finding.
