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
`New → Researching → Contacted →` then either `Interested → In Business` *or* `Uninterested`. New is the default for all owners; In Business is the active-deal end state (the one true terminal — no way out once won). Uninterested is the closed/lost lane, but **reopenable** — it can be moved back to any status so a mis-classified lead is never stranded (amended 2026-06-06). Drives the **My Leads** kanban (one lane per status; New owners are excluded — they live in the **Candidates** view; Uninterested renders as a closed lane but its cards can be dragged back out). Decided 2026-05-30.
_Avoid_: Flags/tags for these (progress is a single funnel position, not a set of booleans); "Called" / "Passed" (superseded by Contacted / Uninterested).

**Explore** (surface):
The **discovery** section of the redesigned app (UI overhaul, 2026-06-06) — **tower-grained** in both its lenses (map points and a ranked long list are both *towers/antennas*, not owners), narrowed by the shared filter set. Each **Freestanding tower** carries its **own** interestingness score and its own detail page (no longer just its owner's rolled-up score); same-owner towers can rank differently. On every tower the **owner** is a visible link that opens the owner page (the **Lead** page) showing all that owner's towers, ranked and filterable. Where you go to *find* an interesting antenna; you don't open it to find an owner. Subsumes today's **Candidates** discovery list and the structures-first map. The act that leaves Explore is **pursuing** a tower → it advances the owner's **Lead** off New into **Manage**.
_Avoid_: Browse, Discover (use Explore), Candidates surface (folds into Explore).

**Leads** (surface):
The **work** section of the redesigned app — **owner-grained** (you call a human, not a tower). Holds every **Lead** the team has moved off New (Researching / Contacted / Interested / In Business, plus the closed Uninterested lane) — i.e. the *worked subset* of all owners; the New/Candidate pool lives in **Explore**. Kanban-by-status + an optional list view; each card shows its **Trigger** tower. Subsumes today's **My Leads** kanban + the **Lead** page. "Where you actually make money."
_Avoid_: My Leads (superseded — this *is* that surface, renamed), Manage / Pipeline / Outreach / Deals (rejected names).

**Trigger** (Lead attribute):
The specific asset — usually a **Freestanding tower** (by ASR number) — whose discovery in **Explore** caused the team to **pursue** its owner, recorded on the resulting **Lead** as outreach context ("flagged from ASR 1287345 — 300ft, Pulaski Co"). Formalizes the existing note in the **Lead** definition that "the antenna is the *reason* a Lead is interesting." A Lead may accumulate more than one trigger over time.
_Avoid_: Reason (too vague), Source (collides with `DataSource`).

**Scoring preset** (UI overhaul, 2026-06-06):
A **named, saved** configuration of the interestingness score — which parameters/
features are included and their weights — that the user creates in the UI and
reuses to rank towers (and, by aggregation, owners). The score is no longer a
fixed formula; a preset *is* the formula, swappable at will. Tenant-shared. Extends
the planned tunable scoring (**ADR-058**) with tower-grain + named presets; a
future ML-learned variant is anticipated.
_Avoid_: Filter (a preset *ranks*; a filter *includes/excludes* — different
operations), Profile, Weighting (use preset for the saved/named whole).

**Antenna override** (UI overhaul, 2026-06-06):
The team's **editable layer over one antenna** (keyed by **ASR**, tenant-scoped),
distinct from the read-only owners index. Carries a hand-entered **address**, an
**archived** flag, and **manual owner details** (name / phone / email / notes).
The owner details exist mainly for an **unowned tower** — one whose landowner we
couldn't auto-resolve (no parcel match → no owner cluster → no **Lead** to hang
them on); such a tower still gets its own openable detail page so the user can
fill in what they find. **Archived** parks an antenna that's been considered but
isn't of interest: it drops out of **Explore**'s map + list until un-archived
(recoverable, never deleted) — surfaced again by the "show archived" filter.
_Avoid_: Antenna note (too narrow — it's also address + archive state), Hidden
(use archived; hidden implies permanent).

**Activity** (event stream):
The time-ordered stream of outreach events on a **Lead** — outbound touches
(call / mail / email), inbound **Replies**, and auto-logged status changes —
backed by the `ContactAttempt` table. The redesign's **calendar** view is this
stream on a timeline. Each event carries a **direction** (outbound | inbound), a
channel, an outcome, a note, and a date.
_Avoid_: History, Log (use Activity for the stream; an entry is an *activity event*).

**Reply** (inbound activity):
An **inbound** Activity event — the signal that an owner responded to outreach.
Logged **manually** today ("Log reply"); a future Gmail integration will auto-fill
the same inbound events. Distinct from a **Lead status** change: a reply can arrive
with no status move (e.g. "who is this?"), and the auto follow-up rule keys on the
*presence/absence of a reply*, not on status.
_Avoid_: Response (ok as prose, but Reply is the canonical term), Interested (a
status, not the inbound event).

**Task** (work item):
A unit of work in the redesigned app's single, filterable **Tasks** workspace —
an outreach follow-up, a general business task, or an internal/dev todo, all the
same entity. Optionally links to an **owner** (Lead) and/or a **tower** (ASR),
optionally **assigned** to a team member (a tenant `User`), with a due date,
status, priority, and category. Created **manually** now; **auto**-created variants
(e.g. follow-ups generated by a rule) come later. There is one Tasks view; the
different "kinds" are distinguished by **filtering**, not by separate surfaces.
_Avoid_: Todo / Follow-up / Reminder (not separate entities — each is a Task
distinguished by its category + links), Ticket (collides with issue tracker).

**Dashboard** (surface):
The **landing** section of the redesigned app and one of the three top-level pages
(**Dashboard · Explore · Leads**). A **hub of digests** — a quick view of several
things, each expandable to a full **sub-page**: an **Attention** feed (replies to
handle + items needing action), a **Tasks** digest (due today/tomorrow + high
priority) → the **Tasks** workspace, a **Calendar** digest → the full **Calendar**,
a **History** digest → the full **History**, and a **Stats** digest → the **Stats**
sub-page. Where you land to see what needs doing and what's been done. Tasks /
Calendar / History / Stats are **sub-pages of Dashboard**, not top-level sections.
_Avoid_: Home (use Dashboard), Overview; calling Tasks/Calendar/Stats "pages" at
the top level (they are Dashboard sub-pages).
