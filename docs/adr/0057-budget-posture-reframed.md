# ADR-057: Budget posture reframed; LLC-unmasking ADR narrowed

**Status:** Accepted
**Revises:** ADR-010 (strict free-only data budget), ADR-041 (no LLC unmasking)
**Date:** 2026-05-25

## Context

Two legacy ADRs were written as "permanent" or hard non-goals during the pitch cut:

- **ADR-010** — "Strict free-only data budget." No paid data (Regrid, ATTOM, CoreLogic, paid SaaS) until / unless explicitly unlocked.
- **ADR-041** — "No LLC unmasking (permanent non-goal)." Resolving the human behind an LLC is sensitive, expensive, and a separate product; this repo never implements it.

In the 2026-05-25 grill the user explicitly said:

> "the goal here is to get as much data as possible so in the future we will have to look into how to start paying for and accessing more data."

Separately, the co-founder's outreach workflow needs **contact info beyond mailing address**. For LLC-owned parcels (heavily weighted in AR — 222K LLCs), parcel data gives an LLC name + a registered-agent address, not the human officer to call. Without a contact path, Phase 1 produces leads the co-founder can't work.

## Decision

**ADR-010 reframes from "permanent stance" to "current-budget posture."**

- Free-only is the *current* posture for Phase 1 — the budget is bounded.
- Paid-data unlocks are expected post-Phase-1 / Phase-2 — Regrid statewide parcels, Steel-in-the-Air paid tier (granular lease comps), CoStar / ATTOM / mortgage feeds for rooftop (ADR-054), paid skip-trace for contact enrichment.
- Anchor states + free-data set remain the Phase 1 sourcing strategy.

**ADR-041 narrows to "paid skip-trace + shell-piercing only."**

- *In scope* for Phase 1 (slice 4 D+E lead-detail panel): **free public-records officer disclosure.** Secretary of State business-entity lookups (free in all 4 anchor states; LLC managers / officers are publicly disclosed *by the entity itself*) + UCC-1 filings get baked into the lead-detail panel as one-click helpers + a snail-mail letter generator.
- *Still out* of Phase 1: paid skip-trace (Whitepages Pro, Cole Information, IDI, Pipl), aggressive identity-resolution / shell-piercing, anything FCRA-adjacent.
- The narrowed posture preserves the spirit of ADR-041 (no sensitive paid investigations) without locking out the routine officer-disclosure surface the co-founder actually needs.

## Consequences

- Phase 1 contact-data path: surface LLC + mailing + one-click SoS lookup links + UCC-1 search; co-founder does any remaining research per lead. Estimated ~1 week added to Slice 4.
- Phase 2 / Phase 3 paid-data conversations open up.
- No change to data already on disk.
- No change to ADR-040 (parcel-owner data is PII; private repo; access controls before public hosting).

## Alternatives considered

- **Keep both ADRs as written:** Phase 1 product is unworkable without contact path beyond mailing; user's "as much data as possible" framing explicitly retires free-only-forever stance. Rejected.
- **Integrate paid skip-trace in Phase 1:** breaks current budget posture, introduces FCRA-adjacent custody, conflates a feature flag with the ADR's sharp edge. Rejected.
