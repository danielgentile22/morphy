# CONTEXT

Domain language and mental model for this repo. Read this before exploring the codebase.

This file is intentionally a stub — the `/grill-with-docs` skill fills it in lazily as domain terms get resolved during real conversations. Until then, the canonical sources of domain language are:

- [PROJECT_BRIEF.md](PROJECT_BRIEF.md) — what the business does and the data problem it solves
- [docs/SCOPE.md](docs/SCOPE.md) — what's in/out right now (anchor states, source list)
- [docs/GLOSSARY.md](docs/GLOSSARY.md) — defined terms
- [docs/DECISIONS.md](docs/DECISIONS.md) — locked design choices (legacy ADRs ADR-001..051; new ADRs go in `docs/adr/`)

## Core concepts (one-line)

- **Asset** — a piece of infrastructure on someone's land (initially: a cell tower from FCC ASR).
- **Landowner** — the party who owns the parcel under an asset; identified by joining ASR coordinates → state parcel data.
- **Ground lease** — the contract between landowner and infrastructure operator; the business helps landowners renegotiate these.
- **Distress overlay** — HUD OZ/QCT, USDA distress, ARC distress; used to prioritize outreach to landowners likely to renegotiate.
- **Anchor states** — the pilot's geographic cut: AR (`05`), NC (`37`), MT (`30`), and FL (`12`) as a stretch.
- **Normalizer / Join / View** — the three-stage preprocess framework (see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

Expand this file when a real conversation surfaces a term that wasn't obvious.

## Language

Terms added as design conversations crystallize them. Follow the format
`**Term**: one-or-two-sentence definition. _Avoid_: aliases.`

**ParcelAdapter**:
The per-source description that lets the shared parcel driver normalize one upstream parcel feed into canonical `parcel` rows. A dataclass holding the source's `field_map`, a `state_fips` hint, and optional `county_resolver` / `post_map` callables. One `ParcelAdapter` per `source_id`, so FL has two (`fl_fgdl_parcels`, `fdor_nal`).
_Avoid_: ParcelMapping, ParcelProfile, ParcelSchema, ParcelSource (the last collides with the fetch-side `DataSource`).

**Registrant**:
The entity listed on FCC ASR `EN.dat` — the party that registered the antenna structure with the FCC. Often the original builder; frequently sold since. Distinct from the *current* tower owner (see **Vendor**).
_Avoid_: Tower owner (ambiguous), ASR owner.

**Vendor**:
The tower-co that *currently* owns the antenna structure and collects rent from carriers — Crown Castle, American Tower (ATC), SBA, Vertical Bridge. Not directly recorded in any free dataset; inferred from FCC ASR Registrant for un-sold towers, or from recorded-lease lessee names for sold towers. Not the wireless service (see **Carrier**).
_Avoid_: Provider, Tower owner (ambiguous — could mean Registrant), Operator.

**Carrier**:
The wireless service (AT&T, Verizon, T-Mobile, Dish) that leases antenna space *from the Vendor*. Sourced from FCC ULS by joining licenses to ASR locations. Not the tower owner (see **Vendor**).
_Avoid_: Provider, Tenant (ambiguous — collides with building tenants in rooftop context).

**Freestanding tower**:
A standalone antenna structure (monopole, lattice, guyed) ≥ 200 ft or near an airport, registered in FCC ASR. The current pipeline's primary asset — **Phase 1** of the product scope.
_Avoid_: Tower (ambiguous when both Freestanding and Rooftop are in conversation), Site.

**Rooftop installation**:
An antenna or DAS installation on a commercial building. Usually under the 200 ft FCC ASR threshold so largely *absent* from ASR. Different data foundation entirely (building cap rate, tenant mix, mortgage status — mostly paid). Out of scope for Phase 1; deferred to **Phase 2**.
_Avoid_: Site (ambiguous), DAS (a subset).

**Triage** (workflow):
The co-founder's working session inside the product — filter parcels/towers across anchor states, rank by interestingness, drill into a candidate, mark as "working" / "passed" / "called", and export or persist lead state. The product's primary user-flow once Phase 1 ships.
_Avoid_: Outreach (broader — includes the actual email/call layer, which is Phase 2).
