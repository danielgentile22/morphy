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
The co-founder's working session inside the product — filter parcels/towers across anchor states, rank by interestingness, drill into a **Lead**, mark its progress, and persist lead state. The product's primary user-flow once Phase 1 ships.
_Avoid_: Outreach (broader — includes the actual email/call layer, which is Phase 2).

**Lead**:
The unit of outreach tracking in the product — keyed to the **Landowner** (an owner cluster), *not* to a single parcel or antenna, and resolved **across all anchor states** (national grain). Aggregates every parcel a landowner holds across the pilot's anchor states plus every structure (antenna, solar, billboard) on those parcels, and carries the user-entered tracking state: contact info, a progress stage (e.g. new → called → interested), and free-text notes. One landowner = one Lead even when they own many parcels/towers in several states, so a single phone call maps to a single record. The antenna/parcel is the *reason* a Lead is interesting; the Lead is *who you call*. (Decided 2026-05-30: the per-landowner grain won over per-antenna and per-parcel because contact/called/notes are owner-level facts; the cross-state grain won over within-state because a national portfolio owner is genuinely one outreach target. Builds on **ADR-056** (Lead = owner-cluster as the triage primitive) and extends it to the cross-state grain. Consequence: owner identity must be resolved *across* states — the pipeline clusters within a state today, and ADR-024's `SHA1(normalized name + address)` cluster key, while stable across recomposes, would *split* a national owner across their regional mailing addresses; cross-state merge therefore needs name-anchored clustering plus the manual merge/split + `display_cluster_id` override path already specified in ADR-056.)
_Avoid_: Antenna page, Parcel record (both are narrower — they are *surfaced within* a Lead).

**Candidate**:
An owner still at **Lead status** = New — i.e. surfaced by the system but not yet worked. Not a separate population from a Lead: every owner has a status (default New), so a Candidate *is* a Lead at its initial state. The **Candidates** surface is the discovery view — owners at New, ranked by interestingness; the millions of untouched owners live here. "Start tracking" a candidate just means advancing its status to Researching (decided 2026-05-30: status is universal, with no separate save/tracked flag).
_Avoid_: Prospect, Saved lead (a Lead is "saved" the moment its status moves off New).

**Lead status**:
The single progress state every Lead carries (exactly one at a time). The ladder, which **branches** after Contacted:
`New → Researching → Contacted →` then either `Interested → In Business` *or* `Uninterested` (terminal). New is the default for all owners; Uninterested is a closed/dead end; In Business is the active-deal end state. Drives the **My Leads** kanban (one lane per status; New owners are excluded — they live in the **Candidates** view; Uninterested is a closed lane). Decided 2026-05-30.
_Avoid_: Flags/tags for these (progress is a single funnel position, not a set of booleans); "Called" / "Passed" (superseded by Contacted / Uninterested).
