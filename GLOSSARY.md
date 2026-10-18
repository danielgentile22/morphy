# Glossary

The mental model and the product language for this repo, plus an A-Z reference of every
domain term used across the docs and code. Read this before exploring the codebase.

The project is archived. Terms for features that were designed but never built say so.

Related sources:

- [docs/STATUS.md](docs/STATUS.md) records what shipped and where the project stopped (anchor states, source list, slice plan).
- [docs/DECISIONS.md](docs/DECISIONS.md) is the ADR index. All ADR bodies live in `docs/adr/`.

## Core concepts

- **Asset**: a piece of infrastructure on someone's land. In Phase 1, a cell tower from the FCC Antenna Structure Registration (ASR).
- **Landowner**: the party who owns the parcel under an asset, identified by joining ASR coordinates to state parcel data.
- **Ground lease**: the contract between a landowner and an infrastructure operator. The product helped landowners renegotiate these.
- **Distress overlay**: the canonical type for spatial-polygon distress designations: HUD Opportunity Zones (OZ) and Qualified Census Tracts (QCT), Appalachian Regional Commission (ARC) counties, and USDA persistent poverty. Parcels are tagged with `in_oz`, `in_qct`, `distress_tier`, and `persistent_poverty`, which feed the score used to rank leads.
- **Anchor states**: the committed Phase 1 cut: AR (`05`), MT (`30`), FL (`12`), WV (`54`). NC (`37`) was a deferred Phase 1 stretch. See [docs/STATUS.md](docs/STATUS.md).
- **Preprocess pipeline**: Normalizer, then Join, then View, run per state by the Composer. Each stage has its own entry in the A-Z reference below; the design is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Product language

Each entry follows the format `**Term**: one-or-two-sentence definition. _Avoid_: aliases.`
This section is the authority for these terms; the A-Z reference does not repeat them.

**ParcelAdapter**:
The per-source description that lets the shared parcel driver normalize one upstream parcel feed into canonical `parcel` rows. A dataclass holding the source's `field_map`, a `state_fips` hint, and optional `county_resolver` / `post_map` callables. One `ParcelAdapter` per `source_id`, so FL has two (`fl_fgdl_parcels`, `fdor_nal`).
_Avoid_: ParcelMapping, ParcelProfile, ParcelSchema, ParcelSource (the last collides with the fetch-side `DataSource`).

**Registrant**:
The entity listed on FCC ASR `EN.dat`: the party that registered the antenna structure with the FCC. Often the original builder, and frequently sold since. Distinct from the *current* tower owner (see **Vendor**).
_Avoid_: Tower owner (ambiguous), ASR owner, Entity.

**Vendor**:
The tower company that *currently* owns the antenna structure and collects rent from carriers: Crown Castle, American Tower (ATC), SBA, Vertical Bridge. Not directly recorded in any free dataset. The plan was to infer it from the FCC ASR Registrant for unsold towers (Slice B) or from recorded-lease lessee names for sold towers. Neither was built. Not the wireless service (see **Carrier**).
_Avoid_: Provider, Tower owner (ambiguous, could mean Registrant), Operator.

**Carrier**:
The wireless service (AT&T, Verizon, T-Mobile, Dish) that leases antenna space *from the Vendor*. Sourced from the FCC Universal Licensing System (ULS) by joining licenses to ASR locations. Not the tower owner (see **Vendor**).
_Avoid_: Provider, Tenant (ambiguous, collides with building tenants in the rooftop context and with the backend **Tenant**).

**Freestanding tower**:
A standalone antenna structure (monopole, lattice, guyed) 200 ft or taller, or near an airport, registered in FCC ASR. The pipeline's primary asset and the whole of **Phase 1** ([ADR-054](docs/adr/0054-asset-universe-phase-1-2.md)).
_Avoid_: Tower (ambiguous when both Freestanding and Rooftop are in conversation), Site.

**Rooftop installation**:
An antenna or distributed antenna system (DAS) installation on a commercial building. Usually under the 200 ft FCC ASR threshold, so largely *absent* from ASR. It needs a different data foundation entirely (building capitalization rate, tenant mix, mortgage status, mostly paid). Out of scope for Phase 1 and deferred to **Phase 2** ([ADR-054](docs/adr/0054-asset-universe-phase-1-2.md)).
_Avoid_: Site (ambiguous), DAS (a subset).

**Triage** (workflow):
The user's working session inside the product: filter parcels and towers across anchor states, rank by interestingness, drill into a **Lead**, advance its **Lead status**, log activity, and export. The product's primary user flow.
_Avoid_: Outreach (broader: it includes the actual email and call layer, which was planned for Phase 2 and never built).

**Lead**:
The unit of tracking in the product. It is keyed to the **Landowner** (an owner cluster, via `display_cluster_id`, [ADR-056](docs/adr/0056-lead-equals-owner-cluster.md)), *not* to a single parcel or antenna, and resolved **across all anchor states** (national grain). It aggregates every parcel a landowner holds across the anchor states plus every structure (antenna, solar, billboard) on those parcels, and carries the user-entered tracking state: contact info, contact attempts, a **Lead status**, and free-text notes. One landowner is one Lead even when they own many parcels and towers in several states, so a single phone call maps to a single record. The antenna or parcel is the *reason* a Lead is interesting; the Lead is the person to contact.
Decided 2026-05-30. The per-landowner grain won over per-antenna and per-parcel because contact, called, and notes are owner-level facts. The cross-state grain won over within-state because a national portfolio owner is genuinely one contact. This builds on ADR-056 (Lead equals owner cluster as the triage primitive) and extends it to the cross-state grain. The consequence is that owner identity must be resolved *across* states. At the time the pipeline clustered within a state, and ADR-024's `SHA1(normalized name + address)` cluster key, while stable across recomposes, would *split* a national owner across their regional mailing addresses. Cross-state merge therefore needed name-anchored clustering plus the manual merge/split and `display_cluster_id` override path specified in ADR-056 (see also [ADR-075](docs/adr/0075-cross-state-owner-identity.md)).
_Avoid_: Antenna page, Parcel record (both are narrower; they are *surfaced within* a Lead).

**Candidate**:
An owner still at **Lead status** New, that is, surfaced by the system but not yet worked. Not a separate population from a Lead. Every owner has a status (default New), so a Candidate *is* a Lead at its initial state. The **Candidates** surface was the discovery view: owners at New, ranked by interestingness, where the millions of untouched owners lived. "Start tracking" a candidate just means advancing its status to Researching (decided 2026-05-30: status is universal, with no separate save or tracked flag).
_Avoid_: Prospect, Saved lead (a Lead is "saved" the moment its status moves off New).

**Lead status**:
The single progress state every Lead carries (exactly one at a time). The ladder **branches** after Contacted:
`New → Researching → Contacted →` then either `Interested → In Business` *or* `Uninterested`. New is the default for all owners. In Business is the one true terminal state, with no way out once reached. Uninterested is the closed lane, but it is **reopenable**: it can be moved back to any status so a misclassified lead is never stranded (amended 2026-06-06). Status drives the **Leads** kanban, one lane per status. New owners are excluded there because they live in **Explore**. Uninterested renders as a closed lane, but its cards can be dragged back out. Decided 2026-05-30.
_Avoid_: Flags or tags for these (progress is a single funnel position, not a set of booleans); "Called" / "Passed" (superseded by Contacted / Uninterested).

**Explore** (surface):
The **discovery** section of the redesigned app (UI overhaul, 2026-06-06, [ADR-067](docs/adr/0067-tower-grained-explore.md)). It is **tower-grained** in both its lenses: map points and a ranked long list are both *towers*, not owners, narrowed by the shared filter set. Each **Freestanding tower** carries its **own** interestingness score and its own detail page, so same-owner towers can rank differently. On every tower the **owner** is a visible link that opens the owner page (the **Lead** page) showing all that owner's towers, ranked and filterable. Explore is where you *find* an interesting antenna; you don't open it to find an owner. It subsumed the earlier **Candidates** discovery list and the structures-first map. The act that leaves Explore is **pursuing** a tower, which advances the owner's **Lead** off New and into **Leads**.
_Avoid_: Browse, Discover (use Explore), Candidates surface (folded into Explore).

**Leads** (surface):
The **work** section of the redesigned app. It is **owner-grained**, because you contact a person, not a tower. It holds every **Lead** the team has moved off New (Researching, Contacted, Interested, In Business, plus the closed Uninterested lane): the *worked subset* of all owners. The New pool lives in **Explore**. It offers a kanban by status plus an optional list view, and each card shows its **Trigger** tower. It subsumed the earlier **My Leads** kanban and the **Lead** page.
_Avoid_: My Leads (superseded; this *is* that surface, renamed), Manage, Pipeline, Outreach, Deals (rejected names).

**Trigger** (Lead attribute):
The specific asset, usually a **Freestanding tower** (by ASR number), whose discovery in **Explore** caused the team to **pursue** its owner. It is recorded on the resulting **Lead** as context ("flagged from ASR 1287345, 300ft, Pulaski Co"). It formalizes the note in the **Lead** definition that the antenna is the *reason* a Lead is interesting. A Lead may accumulate more than one trigger over time.
_Avoid_: Reason (too vague), Source (collides with `DataSource`).

**Scoring preset** (UI overhaul, 2026-06-06):
A **named, saved** configuration of the **Interestingness score** (which parameters and features are included, and their weights) that the user creates in the UI and reuses to rank towers and, by aggregation, owners. The score is not a fixed formula; a preset *is* the formula, swappable at will. Presets are tenant-shared. They extend the tunable scoring of [ADR-058](docs/adr/0058-tunable-transparent-scoring.md) with tower grain and named presets. A machine-learned variant was considered but never built.
_Avoid_: Filter (a preset *ranks*; a filter *includes or excludes*), Profile or Scoring profile (the earlier name), Weighting (use preset for the saved, named whole).

**Antenna override** (UI overhaul, 2026-06-06):
The team's **editable layer over one antenna** (keyed by **ASR**, tenant-scoped), distinct from the read-only owners index. It carries a hand-entered **address**, an **archived** flag, and **manual owner details** (name, phone, email, notes). The owner details exist mainly for an **unowned tower**: one whose landowner could not be auto-resolved (no parcel match, so no owner cluster and no **Lead** to hang it on). Such a tower still gets its own openable detail page so the user can fill in what they find. **Archived** parks an antenna that was considered but is not of interest. It drops out of **Explore**'s map and list until unarchived (recoverable, never deleted), and the "show archived" filter surfaces it again.
_Avoid_: Antenna note (too narrow, since it also holds address and archive state), Hidden (use archived; hidden implies permanent).

**Activity** (event stream):
The time-ordered stream of contact events on a **Lead**: outbound touches (call, mail, email), inbound **Replies**, and auto-logged status changes. Backed by the `ContactAttempt` table. The redesign's **calendar** view is this stream on a timeline. Each event carries a **direction** (outbound or inbound), a channel, an outcome, a note, and a date.
_Avoid_: History, Log (use Activity for the stream; an entry is an *activity event*).

**Reply** (inbound activity):
An **inbound** Activity event, the signal that an owner responded ([ADR-066](docs/adr/0066-inbound-event-reply-seam.md)). Logged **manually** ("Log reply"). A Gmail integration that would auto-fill the same inbound events was planned but never built. Distinct from a **Lead status** change: a reply can arrive with no status move (for example "who is this?"), and the auto follow-up rule keys on the *presence or absence of a reply*, not on status.
_Avoid_: Response (fine as prose, but Reply is the canonical term), Interested (a status, not the inbound event).

**Task** (work item):
A unit of work in the redesigned app's single, filterable **Tasks** workspace: a follow-up on a lead, a general team task, or an internal development todo, all the same entity. It optionally links to an **owner** (Lead) and/or a **tower** (ASR), is optionally **assigned** to a team member (a tenant `User`), and has a due date, status, priority, and category. Tasks are created **manually**. Auto-created variants (for example follow-ups generated by a rule) were planned but never built. There is one Tasks view; the different kinds are distinguished by **filtering**, not by separate surfaces.
_Avoid_: Todo, Follow-up, Reminder (not separate entities; each is a Task distinguished by its category and links), Ticket (collides with the issue tracker).

**Dashboard** (surface):
The **landing** section of the redesigned app and one of the three top-level pages (**Dashboard, Explore, Leads**; [ADR-065](docs/adr/0065-redesign-three-section-ia.md)). A **hub of digests**: a quick view of several things, each expandable to a full **sub-page**. It holds an **Attention** feed (replies to handle and items needing action), a **Tasks** digest (due today or tomorrow, plus high priority) that opens the **Tasks** workspace, a **Calendar** digest that opens the full **Calendar**, a **History** digest that opens the full **History**, and a **Stats** digest that opens the **Stats** sub-page. It is where you land to see what needs doing and what has been done. Tasks, Calendar, History, and Stats are **sub-pages of Dashboard**, not top-level sections.
_Avoid_: Home (use Dashboard), Overview; calling Tasks, Calendar, or Stats "pages" at the top level (they are Dashboard sub-pages).

## A-Z reference

Domain terms used across the docs and code. Product-language terms (Carrier, Freestanding
tower, Lead, Registrant, Rooftop installation, Scoring preset, Triage, Vendor, and the rest)
are defined once in the section above.

### A

- **ACS**: American Community Survey. The Census Bureau's rolling demographic and socio-economic survey. Its 5-year aggregates are the workhorse for tract-level poverty and income data.
- **ADR**: Architecture Decision Record. One file per decision under `docs/adr/`; `docs/DECISIONS.md` is the index.
- **APN**: Assessor's Parcel Number. The county-assigned identifier for a parcel. Synonyms: PIN (Parcel Identification Number), `parcel_id` (our canonical name).
- **ARC**: Appalachian Regional Commission. The federal agency that classifies counties in the Appalachian region by economic-status tier (Distressed, At-Risk, Transitional, Competitive, Attainment).
- **ArcGIS**: Esri's geographic information system (GIS) product family. Many federal and state publishers expose datasets via ArcGIS REST services or hosted ArcGIS Online portals.
- **ASR**: Antenna Structure Registration. The FCC's registry of antenna structures 200 ft or taller, or near airports. Each entry has an ASR registration number, structure coordinates, height, type, status, and registrant entity. Our primary tower-locations source.
- **AutomationPolicy**: a per-source enum on every `DataSource` declaring how the puller may fetch it: `ALLOWED`, `TOLERATED`, `MANUAL_ONLY`, `CREDENTIALED`. See [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

### B

- **Backend**: the FastAPI and SQLAlchemy service alongside the static map app. It holds lead and task state, contact attempts, the activity log, scoring presets and settings, and owner merge/split overrides, behind username/password auth ([ADR-062](docs/adr/0062-username-password-replaces-magic-link.md), [ADR-063](docs/adr/0063-file-credentials-teams-per-request-authority.md), [ADR-069](docs/adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)). It ran on SQLite on a Fly volume, replicated by Litestream to R2 ([ADR-064](docs/adr/0064-phase1-hosting-fly-sqlite.md)). Lease-document storage in R2 and Claude API extraction were planned (Slice D+E) but never built. See [ADR-055](docs/adr/0055-hosted-private-backend.md) and [backend/README.md](backend/README.md).
- **BLM / BIA**: Bureau of Land Management and Bureau of Indian Affairs. Federal landholders whose parcels may not appear in county-level tax rolls.

### C

- **Cadastral**: relating to legal land boundaries and parcels. "MT Cadastral" is Montana's statewide parcel layer.
- **CAMA**: Computer Assisted Mass Appraisal. The county tax assessor's parcel-attribute database, and the upstream of NC OneMap and similar state-aggregated parcel feeds.
- **Canonical type**: a project-internal schema (for example `parcel`, `tower`, `distress_overlay`, `lead`) that every Normalizer maps its raw data into. See `scripts/preprocess/base.py`.
- **Catalog**: the per-state `catalog.json` written by the Composer, describing every layer and view available for that state. The map app reads it to populate the UI.
- **CDFI**: Community Development Financial Institution. A Treasury designation; CDFI Investment Areas are a distress overlay.
- **Composer**: `scripts/preprocess/compose.py`. For one state FIPS code it loads canonical data, runs Joins in dependency order, runs Views, and writes per-state outputs plus `catalog.json` and `summary.json`.
- **Composite**: the per-state output produced by the Composer. Lives at `data/processed/composite/<fips>/`.

### D

- **DMS**: Degrees / Minutes / Seconds. The coordinate format FCC ASR uses; we convert to decimal degrees during normalize.
- **DSL**: Division of State Lands (Florida). Publishes a parcel layer of *state-owned* land, **not** the FDOR NAL tax-roll layer we actually want. See ADR-019.

### E

- **EIA**: U.S. Energy Information Administration. Publishes Form 860 (annual) and 860M (monthly), utility-scale power-plant inventories with plant location, owner, and capacity.
- **Entity (FCC ASR)**: the registrant of an antenna structure as recorded in `EN.dat` of the ASR bulk data. Not the *landowner* under the tower; that is a separate join. See **Registrant**.
- **EPSG**: coordinate reference system (CRS) codes from the European Petroleum Survey Group. EPSG:4326 is WGS84 lat/lon (the web standard). EPSG:2264 is NC State Plane (US survey feet).

### F

- **FAA OEAAA**: FAA Obstruction Evaluation / Airport Airspace Analysis. Records of proposed and recently built tall structures, a forward-looking pipeline of towers.
- **FCC**: Federal Communications Commission. Publishes ASR (tower registrations) and ULS (radio-service licenses).
- **FDOR**: Florida Department of Revenue. Publishes the NAL tax-roll dataset per county.
- **FDOT**: Florida Department of Transportation. Publishes outdoor advertising (billboard) permits.
- **FGDL**: Florida Geographic Data Library. Aggregates various FL state datasets. It published DSL (state-land) parcels, **not** FDOR NAL.
- **FIPS**: Federal Information Processing Standards. We use the state FIPS code (for example `37` = NC, `05` = AR) and the county FIPS code (for example `075` for Graham County in NC, full GEOID `37075`).

### G

- **GeoJSON**: the RFC 7946 JSON-based geometry format. What the map app reads for catalog and view layers. Large-row layers are skipped per ADR-052; parcels render from PMTiles.
- **GeoParquet**: Apache Parquet with a standard geometry column encoding. Our canonical analytical format. About 5-10x smaller than GeoJSON, and it supports column projection.

### H

- **HIFLD**: Homeland Infrastructure Foundation-Level Data. Infrastructure datasets curated by the Department of Homeland Security (DHS). It **retired** the public cellular-towers layer in 2024 (ADR-015).
- **HUD**: U.S. Department of Housing and Urban Development. Publishes OZ (Opportunity Zones) and QCT (Qualified Census Tracts).

### I

- **Interestingness score**: a composite per-tower and per-parcel score in [0, 1] used to rank leads. Components: infrastructure presence, distress overlap, owner kind (LLCs and trusts weighted), cluster size. Implementation: `scripts/preprocess/scoring.py`. It is **tunable and transparent** (Slice C, shipped, [ADR-058](docs/adr/0058-tunable-transparent-scoring.md)): components are stored in parquet, weights are set client-side via UI sliders, and named **Scoring presets** are persisted per tenant. Per-tower scoring landed with owners-index schema v5.

### J

- **Join**: `scripts/preprocess/joins/<name>.py`. Mutates one canonical layer with attributes from another (for example `TowerToParcelJoin` adds `parcel_id` to towers). Joins run in topological order via `ordered_joins()`.

### L

- **LBNL Tracking the Sun**: the Lawrence Berkeley National Lab dataset of US rooftop and distributed photovoltaic (PV) installations. Dropped from the active registry (ADR-016).
- **Lease**: the planned carrier-side ground-lease record, keyed on `(parcel_id, tower_asr_id, carrier_callsign)`, with the state machine unknown → pending_upload → uploaded → extracted → verified → superseded. Document storage and LLM-extracted structured fields were to land here in Slice D+E ([ADR-059](docs/adr/0059-llm-lease-extraction.md)). Never built.
- **Lease extraction**: the Slice D+E pipeline designed to turn an uploaded lease PDF into structured fields (rent, escalation, expiry, amendment count, parties, and so on) plus per-field confidence, via the Claude API. The design used Sonnet 4.6 by default with an Opus 4.7 retry path for low-confidence leases, and prompt caching on. See [ADR-059](docs/adr/0059-llm-lease-extraction.md). Designed only; never built.
- **`lease_comp`**: a planned per-area lease-rent benchmark table, meant to be bootstrapped from free county-level data in Slice D+E and augmented by rent from extracted leases. It would have powered a "comparables within X-mile radius" feature. Never built (see **Steel-in-the-Air**).
- **libpostal**: a native C library for international address normalization. It was the preferred option for the address half of owner-cluster strengthening, with pure-Python `usaddress` as the fallback if dependency management proved painful. Deferred, and superseded as the first fix by the manual merge/split path.
- **LLC unmasking**: the sensitive, expensive process of resolving the people behind a legal entity. **Narrowed in [ADR-057](docs/adr/0057-budget-posture-reframed.md):** paid skip-trace and shell-piercing remained permanent non-goals, while **free public-records officer disclosure** (Secretary of State business-entity lookups, UCC-1 filings) was in scope for the Slice D+E lead-detail panel.

### M

- **Magic-link auth**: passwordless auth via email-delivered one-time links, the original Slice D+E sign-in design ([ADR-055](docs/adr/0055-hosted-private-backend.md)). **Removed** and replaced by **Username/password login** ([ADR-062](docs/adr/0062-username-password-replaces-magic-link.md)).
- **Manifest**: two distinct files in this project:
  - `data/manifest.json` is the fetch manifest: what raw data is on disk.
  - `data/processed/preprocess_manifest.json` is the preprocess manifest: what has been normalized and composed.
- **MANUAL_ONLY**: the AutomationPolicy meaning the puller will not attempt to fetch, and the user must download manually. The puller provides a step-by-step walkthrough.
- **MapLibre GL JS**: the open-source WebGL map renderer (a fork of Mapbox GL JS from before its license change). The map app's rendering engine; see `app/ARCHITECTURE.md`.

### N

- **NAL**: Name, Address, Legal. The Florida Department of Revenue's per-county tax-roll dataset, containing private-owner names and assessed values. The data we actually want for FL (ADR-019).
- **NC OneMap**: North Carolina's geospatial data portal. Publishes standardized statewide parcel data sourced from county CAMA exports. The original test county (Graham County) used this source.
- **Normalizer**: `scripts/preprocess/normalizers/<source>.py`. Reads one raw source and emits one or more canonical-type Parquet files plus a `quality_report.json`.

### O

- **OE/AAA**: see FAA OEAAA.
- **Owner cluster**: a group of parcels sharing the same normalized owner and normalized address pair. Its ID is the SHA1 of the concatenation. Surfaced via the `owner_clusters` view and the `owner_cluster_size` column on parcels. It **became the Lead key in Slice D+E** ([ADR-056](docs/adr/0056-lead-equals-owner-cluster.md)), when ADR-024's algorithm was strengthened with conservative normalization layers and a manual merge/split UI.
- **`owner_cluster_override`**: the backend table storing user-issued manual cluster merges and splits: `(tenant_id, source_cluster_id, target_cluster_id)`. Raw cluster IDs stay in parquet; the backend computes `display_cluster_id = coalesce(override_target, raw_cluster_id)`.
- **owner_kind**: a categorical inferred from owner-name patterns: `llc`, `individual`, `trust`, `corporation`, `gov`, `church`, `partnership`, `school`, `unknown`. Implementation in `scripts/preprocess/cluster.py`.
- **OZ**: Opportunity Zone. A census tract designated under the 2017 Tax Cuts and Jobs Act. The original "OZ 1.0" designations are in effect through about 2028. Governors were scheduled to make "OZ 2.0" redesignations during 2026, so the layer was expected to change.

### P

- **Parcel**: a single legally defined unit of real estate with a unique APN, polygon boundary, owner, mailing address, and assessed value. The atomic geographic unit linking infrastructure to a person or entity. Not the same as a **Lead** (which is the owner cluster).
- **Persistent poverty**: the USDA designation for counties with a poverty rate of 20% or more sustained over the past 30 years or so.
- **Phase 1**: the cut the project built. A product for the committed anchors AR, MT, FL, and WV (NC a deferred stretch), freestanding towers only, in slices F → A → C → D+E → B. See [docs/STATUS.md](docs/STATUS.md) and [ADR-053](docs/adr/0053-product-phase-shift.md).
- **Phase 2**: the expansion after Phase 1: rooftop installations, mass email, the paid Steel-in-the-Air tier, self-serve refresh, and recorded-lease automation. Planned but never built. See [docs/STATUS.md](docs/STATUS.md).
- **PII**: Personally Identifiable Information. Parcel-owner names and mailing addresses meet most PII definitions even when individually public record. See ADR-040 and [docs/SECURITY.md](docs/SECURITY.md).
- **PMTiles**: a single-file format for vector tiles. Friendly to HTTP Range requests, so no tile server is needed. Used for the parcel base layer in the map app.
- **Puller**: the data TUI (`scripts/data_tui/`, `python -m data_tui`), a Textual terminal app for pulling raw data into `data/raw/` and driving preprocess, verify, and deploy. It replaced the retired PySide6 desktop app. See [docs/PULLER_UX.md](docs/PULLER_UX.md).
- **Pyogrio**: a fast geopandas-compatible reader and writer for vector spatial files (shapefile, GDB, GeoJSON). Used in preprocess.

### Q

- **QCT**: Qualified Census Tract. The HUD designation for high-poverty and low-income tracts; one of our distress overlays.

### R

- **Read-only demo**: the public deployment at `morphy-demo.fly.dev`, where "Explore the demo" signs a visitor in with no password as one read-only credential. Read-only is a `credential.read_only` flag; `current_principal` refuses that principal's writes with 403, and the `DEMO_MODE` switch that enables the demo login fails closed at boot. The demo board holds fictional leads from `python -m app.demo_seed` ([ADR-077](docs/adr/0077-read-only-demo-credential.md)). _Avoid_: guest mode, sandbox (no writes happen at all).
- **Regrid**: a paid nationwide standardized parcel and owner data service. Deferred to Phase 2 or later per [ADR-057](docs/adr/0057-budget-posture-reframed.md), which revised ADR-012's "out of scope" framing to "deferred". A stub source is preserved.

### S

- **safe_merge**: a helper in `scripts/preprocess/base.py` that drops pre-existing target columns before a pandas merge, preventing `_x` / `_y` column collisions when a Join adds columns that Normalizers initialize. See ADR-020.
- **Schema version**: an integer field stamped on every canonical output (`_schema_version`). It bumps when the canonical-type schema changes.
- **Skip-trace**: paid contact-data resolution (phone, email, current address) via third-party vendors (Whitepages Pro, Cole Information, IDI, Pipl). A permanent non-goal for Phase 1 per [ADR-057](docs/adr/0057-budget-posture-reframed.md), which narrowed ADR-041.
- **Slice**: one unit of Phase 1 work with its own "shipped" gate. The slices in order: **F** (committed-anchor composes for AR, MT, FL, WV; NC deferred), **A** (carriers via ULS), **C** (asset enrichment and the tunable scoring UI), **D+E** (lease documents, backend, and triage state), **B** (vendor inference). See [docs/STATUS.md](docs/STATUS.md) for the plan and how far each slice got.
- **SoS**: Secretary of State. Each state's SoS publishes business-entity records (LLC formation, officers, registered agent). A one-click SoS helper was in scope for the Slice D+E lead-detail panel ([ADR-057](docs/adr/0057-budget-posture-reframed.md)) but was never built.
- **Spatial join**: assigning attributes from one geographic layer to another based on a spatial relationship (the typical case is point-in-polygon: which parcel contains this tower).
- **Steel-in-the-Air**: a third-party publisher of cell-tower lease-rent benchmarks (Steel in the Air, Inc.). It was used as a reference benchmark only. Its terms forbid reproducing its data beyond limited attributed quotation, so none of its data is in the repo, the pipeline, or the demo. A free county-level dataset from it was assumed to exist as the `lease_comp` bootstrap; on 2026-05-26 that turned out to be false (see [docs/STATUS.md](docs/STATUS.md)). The next-best free path was real estate investment trust (REIT) annual report (10-K) rent disclosures and asset-backed securities (ABS) filings. Its paid tier was deferred to Phase 2 ([ADR-057](docs/adr/0057-budget-posture-reframed.md)).

### T

- **Tenant**: in the backend, a logical isolation unit. Every table has a `tenant_id` column and every route filters by it. **Teams are tenants**: each credential is bound to exactly one tenant (one team), resolved per request ([ADR-063](docs/adr/0063-file-credentials-teams-per-request-authority.md)); there is no `tenant_id = 1` stub. The schema was tenant-shaped from day one so a second team is a row-add, not a refactor ([ADR-055](docs/adr/0055-hosted-private-backend.md)). Not to be confused with **building tenants** in the rooftop context (deferred to Phase 2).
- **testcontainers-postgres**: an opt-in backend test harness that spins up a real Postgres in Docker (`MORPHY_TEST_TESTCONTAINERS=1`) to catch Postgres-specific bugs (JSON operators, isolation levels). The default is SQLite, behaviorally equivalent for the schema; auto-starting Postgres was dropped as too slow. See [docs/TESTING.md](docs/TESTING.md).
- **TIGER**: Topologically Integrated Geographic Encoding and Referencing. The Census Bureau's geospatial reference files.
- **Tippecanoe**: the Mapbox/Felt command-line tool for generating vector tiles (MBTiles, PMTiles) from large GeoJSON or NDJSON inputs. Required for the map app's parcel base layer.
- **TPO**: Third-Party Ownership (of a solar system). Solar installations under a power purchase agreement (PPA) or lease, where the contract can potentially be renegotiated. The solar-side analogue of ground leases.

### U

- **UCC-1**: a Uniform Commercial Code financing statement, filed by secured parties. It was to be surfaced in the Slice D+E lead-detail panel as a third-party-ownership clue for parcel-attached assets; never built.
- **ULS**: Universal Licensing System (FCC). Six bulk data bands plus metadata. **Cellular (Part 22), PCS (Part 24), and AWS / 700 MHz (Part 27) were in Phase 1 Slice A** for carrier identification ([ADR-053](docs/adr/0053-product-phase-shift.md) partially reversed ADR-013; see also [ADR-074](docs/adr/0074-uls-carrier-rearchitecture.md)). Microwave, Ownership, Transfers, and Leasing stayed deferred.
- **USDA ERS**: USDA Economic Research Service. Publishes persistent-poverty and county typology data.
- **Username/password login**: the backend's sign-in front door. Credentials live in the app DB's `credential` table (PBKDF2 hashes, managed via `python -m app.users`) and are exchanged at `POST /api/auth/login` for an identity-only HS256 session JWT set in the httpOnly `morphy_session` cookie. The credential table re-authorizes every request ([ADR-062](docs/adr/0062-username-password-replaces-magic-link.md), [ADR-063](docs/adr/0063-file-credentials-teams-per-request-authority.md), [ADR-069](docs/adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)). It replaced magic-link auth. Mechanics: [backend/README.md](backend/README.md).
- **USPVDB**: US Photovoltaic Database. The USGS and Berkeley Lab dataset of utility-scale solar facility polygons.
- **usaddress**: a pure-Python, US-only address parser. The fallback to libpostal. Narrower coverage, no native dependencies.

### V

- **View**: `scripts/preprocess/views/<name>.py`. A derived dataset built on top of composed canonical data (for example `llc_owned_parcels_with_infra`, `interestingness_top_1000`). Surfaced in the catalog and as map filter toggles.

### W

- **WGS84**: the lat/lon coordinate system used by GPS and web mapping, EPSG:4326. All our output is in this CRS.
