# ADR-053: Product phase shift — pitch demo → co-founder-facing product

**Status:** Accepted
**Date:** 2026-05-25

## Context

The repo was built and documented as a "v1 pitch-quality demo across 4 anchor states" (PROJECT_BRIEF, SCOPE pre-2026-05-25, GOALS pre-2026-05-25). The audience was an investor / co-founder / strategic partner walked through in 10 minutes. Several feature areas were therefore hard non-goals: lease economics, carrier/tenant data, recorded leases, LLC unmasking, mass outreach, document storage.

In a grill session on 2026-05-25 the user explicitly reframed:

> "We're past v1. I need this to be a fully fleshed-out product at this point... I need the software to get to a point where for at least those four states, it works, and you can use this, and you can start looking at the antennas, and you can start ranking them and filtering through them and choosing the ones that he's gonna then follow-up on."

Audience pivoted from "investor walkthrough" to "co-founder daily user." The co-founder shared a detailed product wishlist (carrier IDs, vendor IDs, lease document upload + structured extraction, mass-email + response tracking, comparables, etc.).

## Decision

The project transitions from "pitch cut" to **Phase 1 of a co-founder-facing product**. The 2-person team is: user (software) + co-founder (business; primary user of the product).

**Phase 1 outcome bar:** the co-founder uses the product as his **primary daily triage tool for 4 consecutive weeks**, picking targets from it without falling back to spreadsheets or asking for custom data pulls. Deal-closing is *not* the gate (depends on his pitching + market); usage is the honest proxy.

**Phase 1 in-scope features** (flipped from previous hard non-goals):
- FCC ULS carrier identification per tower (ADR-013 reverses)
- Asset enrichment (billboards + solar on parcel) (ADR-014 partially reverses)
- Vendor (tower-co) inference
- Lease document upload + LLM-based structured extraction with confidence (see ADR-059)
- Triage state / write layer / CSV exports (requires backend — see ADR-055)
- Free public-records contact enrichment (Secretary of State, UCC-1) (see ADR-057)

**Phase 1 anchor states unchanged:** AR + MT + FL + NC. Not nationwide. (ADR-001 state-level scope stays correct.)

**Phase 2** = asset-universe expansion to rooftops (ADR-054) + operational scale (mass email, comparables paid tier, self-serve refresh, recorded-lease automation).

**No fixed timeline.** User: *"I don't care about timelines. Let's set goals and work through them."*

## Consequences

- SCOPE.md, GOALS.md, ROADMAP.md, STATUS.md, CLAUDE.md all rewrite (this ADR drives the rewrites).
- ADR-006 (static-site) superseded by ADR-055; ADR-010 + ADR-041 revised by ADR-057.
- Pitch-cut KPIs in GOALS.md retire; new product per-slice gates (see session summary `docs/grill-2026-05-25-summary.md`) replace them.
- Plan-of-work becomes Slices F → A → C → D+E → B in defined order.

## Alternatives considered

- **Stay with the pitch cut:** rejected by user's explicit reframing.
- **Skip Phase 1, jump to Phase 2 rooftops:** rejected; rooftops require paid data (CoStar / building tenant mix), break free-only posture without delivering anything sooner.
