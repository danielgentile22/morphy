# ADR-053: Product phase shift from demo to daily-use product

**Status:** Accepted
**Date:** 2026-05-25

## Context

The repo was first built and documented as a read-only demo across 4 anchor states, meant for a 10-minute walkthrough. Several feature areas were therefore hard non-goals: lease economics, carrier and tenant data, recorded leases, LLC unmasking, mass outreach, and document storage.

On 2026-05-25 the project was reframed. The tool had to work end to end for the anchor states as the daily triage tool of the product's single analyst user: look at the antennas, rank them, filter them, and pick the ones to follow up on. The analyst's wishlist included carrier IDs, vendor IDs, lease document upload with structured extraction, mass email with response tracking, and lease comparables.

## Decision

The project moves from a demo cut to **Phase 1 of a daily-use product**, with one developer and one analyst as the primary user.

**Phase 1 in-scope features** (flipped from earlier hard non-goals):
- FCC Universal Licensing System (ULS) carrier identification per tower (reverses ADR-013)
- Asset enrichment: billboards and solar on the parcel (partly reverses ADR-014)
- Vendor (tower company) inference
- Lease document upload with LLM-based structured extraction and confidence (see ADR-059)
- Triage state, a write layer, and CSV exports (needs a backend, see ADR-055)
- Free public-records contact enrichment: Secretary of State filings and UCC-1 (Uniform Commercial Code financing statement) records (see ADR-057)

**Phase 1 anchor states are unchanged:** AR, MT, FL and NC. Not nationwide. ADR-001's state-level scope still holds.

**Phase 2** was to be asset-universe expansion to rooftops (ADR-054) plus operational scale: mass email, a paid comparables tier, self-serve refresh, and recorded-lease automation.

**No fixed timeline.** Work proceeds by goals, not dates.

## Consequences

- The scope, status and orientation docs were rewritten around this ADR. The surviving record is [STATUS.md](../STATUS.md).
- ADR-006 (static site) is superseded by ADR-055. ADR-010 and ADR-041 are revised by ADR-057.
- The demo-cut success measures retire. Per-slice gates replace them.
- The plan of work becomes Slices F → A → C → D+E → B, in that order.

## Alternatives considered

- **Stay with the demo cut.** Rejected by the explicit reframing.
- **Skip Phase 1 and go straight to Phase 2 rooftops.** Rejected. Rooftops need paid data (CoStar, building tenant mix), which breaks the free-data posture without delivering anything sooner.
