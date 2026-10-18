# ADR-057: Budget posture reframed; LLC-unmasking ADR narrowed

**Status:** Accepted
**Revises:** ADR-010 (strict free-only data budget), ADR-041 (no LLC unmasking)
**Date:** 2026-05-25

## Context

Two earlier ADRs were written as permanent stances or hard non-goals during the demo cut:

- **ADR-010**, "Strict free-only data budget." No paid data (Regrid, ATTOM, CoreLogic, paid SaaS) unless explicitly unlocked.
- **ADR-041**, "No LLC unmasking (permanent non-goal)." Resolving the person behind an LLC is sensitive, expensive, and a separate product, so this repo never implements it.

The product phase (ADR-053) changed both premises. The data strategy became "collect as much as possible, and pay for more data later."

Separately, triage needs **contact information beyond a mailing address**. For LLC-owned parcels (heavily weighted in AR, with 222K LLCs), parcel data gives an LLC name and a registered-agent address, not the officer to contact. Without a contact path, Phase 1 produces leads nobody can act on.

## Decision

**ADR-010 changes from a permanent stance to the current budget posture.**

- Free-only is the posture for Phase 1, because the budget is bounded.
- Paid sources were left for after Phase 1: Regrid statewide parcels, the Steel-in-the-Air paid tier (granular lease comparables; its free pages served only as a reference benchmark, since its terms forbid reproducing the data beyond limited attributed quotation), CoStar, ATTOM and mortgage feeds for rooftops (ADR-054), and paid skip-trace (commercial people-search lookup) for contact enrichment.
- Anchor states plus the free-data set remain the Phase 1 sourcing strategy.

**ADR-041 narrows to "no paid skip-trace and no shell-piercing."**

- *In scope* for Phase 1 (the Slice D+E lead-detail panel): **free public-records officer disclosure.** Secretary of State (SoS) business-entity lookups are free in all 4 anchor states, and LLC managers and officers are disclosed publicly *by the entity itself*. These, plus UCC-1 (Uniform Commercial Code financing statement) filing searches, go into the lead-detail panel as one-click helpers, along with a mail-letter generator.
- *Still out* of Phase 1: paid skip-trace services (Whitepages Pro, Cole Information, IDI, Pipl), aggressive identity resolution or shell-piercing, and anything covered by the Fair Credit Reporting Act (FCRA).
- The narrowed posture keeps the intent of ADR-041 (no sensitive paid investigations) without blocking the routine officer-disclosure lookups triage needs.

## Consequences

- The Phase 1 contact-data path: show the LLC name and mailing address, one-click SoS lookup links, and UCC-1 search. The analyst does any remaining research per lead.
- Paid data stays possible in later phases.
- No change to data already on disk.
- No change to ADR-040 (parcel-owner data is PII; access controls come before any hosting).

## Alternatives considered

- **Keep both ADRs as written.** The Phase 1 product cannot work without a contact path beyond the mailing address, and the "collect as much as possible" strategy retires the free-only-forever stance. Rejected.
- **Integrate paid skip-trace in Phase 1.** Breaks the current budget posture, brings FCRA-adjacent data custody, and blurs a feature flag into the ADR's hard line. Rejected.
