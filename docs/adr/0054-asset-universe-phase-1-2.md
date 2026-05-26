# ADR-054: Phase 1 freestanding towers; Phase 2 rooftop installations

**Status:** Accepted
**Date:** 2026-05-25
**Pairs with:** ADR-053

## Context

The co-founder's product wishlist (2026-05-25) mixed two distinct asset universes:

- **Freestanding cell towers** — standalone monopoles / lattice / guyed structures ≥ 200 ft or near airports, registered in FCC ASR. Mostly rural. Current pipeline foundation.
- **Rooftop installations** — antennas / DAS on commercial buildings. Mostly under the FCC ASR registration threshold, therefore largely absent from ASR. Mostly urban. Different data foundation.

The co-founder's language frequently said "building" — "tenant occupancy in the building", "building owner", "how tall is the building", "is it part of building power", "remained current with their mortgage payments." Those questions only make sense for rooftop / in-building installations, not freestanding monopoles.

Data foundations differ severely:

| | Freestanding (Phase 1) | Rooftop (Phase 2) |
|---|---|---|
| In FCC ASR | Yes (≥ 200 ft) | Mostly no (under threshold) |
| Landowner = | Parcel owner, usually one obvious entity | Commercial building owner; often LLC; with paying tenants |
| What matters | Distress overlay, parcel value | Building cap rate, tenant mix, mortgage status |
| Vendor universe | Big four (Crown, ATC, SBA, VB) | Specialty firms (Tower Genius, Tower Cloud) |
| Free data | OK | Almost none — paid CoStar territory |
| Anchor states fit | AR/MT (rural); FL/NC (mixed) | FL/NC + dense-urban states; AR/MT have little rooftop volume |

## Decision

Asset-universe split:

- **Phase 1 = freestanding towers only.** Anchor states AR + MT + FL + NC. ASR-registered structures.
- **Phase 2 = rooftop installations.** Different data sourcing strategy (likely paid). Different anchor-state set.

The rooftop-flavoured co-founder wishlist items defer with the rooftop universe: tenant occupancy in the building, building owner mortgage status, building tenant mix, electric meter source, property manager team. None of these are meaningful against a 200 ft monopole in rural Arkansas.

## Consequences

- All Phase 1 work targets freestanding towers; data sourcing stays the existing free-data set.
- Phase 1 co-founder asks that *don't* depend on the rooftop context — carrier IDs, vendor IDs, lease docs, contact enrichment — remain in Phase 1.
- Phase 2 scoping deferred until Phase 1 ships; rooftop sourcing strategy (paid CoStar / LoopNet) is consistent with ADR-057's reframing of ADR-010.
- The repo's existing canonical schemas (`parcel`, `tower`) are freestanding-shaped today and don't need to change for Phase 1. Rooftop in Phase 2 is a new canonical type, not a refactor.

## Alternatives considered

- **Rooftops only:** rejected; ASR pipeline is the wrong foundation for rooftop, all current sourcing investment is for freestanding.
- **Both in Phase 1:** rejected as scope inflation; rooftop data is mostly paid (breaks free-only posture) without delivering sooner.
- **Towers only, no rooftops ever:** rejected; co-founder explicitly wants the rooftop story eventually.
