# ADR-054: Phase 1 freestanding towers; Phase 2 rooftop installations

**Status:** Accepted
**Date:** 2026-05-25
**Pairs with:** ADR-053

## Context

The product wishlist (2026-05-25) mixed two distinct asset universes:

- **Freestanding cell towers.** Standalone monopole, lattice or guyed structures of 200 ft or more, or near airports, registered in the FCC Antenna Structure Registration (ASR). Mostly rural. This is the existing pipeline's foundation.
- **Rooftop installations.** Antennas or distributed antenna systems (DAS) on commercial buildings. Mostly under the ASR registration threshold, so largely absent from ASR. Mostly urban. A different data foundation.

Many wishlist questions were about a building: tenant occupancy, the building owner, building height, whether the site runs on building power, whether the owner is current on the mortgage. Those questions only make sense for rooftop or in-building installations, not freestanding monopoles.

The data foundations differ sharply:

| | Freestanding (Phase 1) | Rooftop (Phase 2) |
|---|---|---|
| In FCC ASR | Yes (200 ft or more) | Mostly no (under threshold) |
| Landowner is | Parcel owner, usually one obvious entity | Commercial building owner, often an LLC, with paying tenants |
| What matters | Distress overlay, parcel value | Building capitalization rate, tenant mix, mortgage status |
| Vendor universe | Big four (Crown, ATC, SBA, VB) | Specialty firms (Tower Genius, Tower Cloud) |
| Free data | Adequate | Almost none; paid CoStar territory |
| Anchor-state fit | AR/MT (rural); FL/NC (mixed) | FL/NC plus dense-urban states; AR/MT have little rooftop volume |

## Decision

Split the asset universe:

- **Phase 1 is freestanding towers only.** Anchor states AR, MT, FL and NC. ASR-registered structures.
- **Phase 2 is rooftop installations.** A different data sourcing strategy (likely paid) and a different anchor-state set.

The rooftop-specific wishlist items defer with the rooftop universe: building tenant occupancy, building owner mortgage status, building tenant mix, electric meter source, and property manager. None of these mean anything for a 200 ft monopole in rural Arkansas.

## Consequences

- All Phase 1 work targets freestanding towers. Data sourcing stays on the existing free-data set.
- Wishlist items that do not depend on the rooftop context (carrier IDs, vendor IDs, lease documents, contact enrichment) stay in Phase 1.
- Phase 2 scoping waits for Phase 1. A paid rooftop sourcing strategy (CoStar, LoopNet) is consistent with ADR-057's reframing of ADR-010.
- The existing canonical schemas (`parcel`, `tower`) are freestanding-shaped and need no change for Phase 1. Rooftop in Phase 2 would be a new canonical type, not a refactor.

## Alternatives considered

- **Rooftops only.** Rejected. The ASR pipeline is the wrong foundation for rooftops, and all existing sourcing work targets freestanding towers.
- **Both in Phase 1.** Rejected as scope inflation. Rooftop data is mostly paid, which breaks the free-only posture, and it would not deliver anything sooner.
- **Towers only, rooftops never.** Rejected. The rooftop universe was a wanted later phase.
