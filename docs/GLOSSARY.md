# GLOSSARY — Domain Terms

**Last updated:** 2026-06-26

The A–Z reference of record for every domain-specific term used across the docs and code. If
a doc uses a term not defined here, file a fix.

For the **mental model + product-language slice** (Lead / Candidate / Trigger / Vendor /
Carrier / Registrant / Freestanding / Triage / Explore / …), [`CONTEXT.md`](../CONTEXT.md) at
the repo root is the authority; the entries below stay consistent with it.

---

## A

- **ACS** — American Community Survey. The Census Bureau's rolling demographic + socio-economic survey; 5-year aggregates are the workhorse for tract-level poverty / income data.
- **ADR** — Architecture Decision Record. One file per decision under `docs/adr/`; `docs/DECISIONS.md` is the index.
- **APN** — Assessor's Parcel Number. The county-assigned identifier for a parcel. Synonyms: PIN (Parcel Identification Number), `parcel_id` (our canonical name).
- **ARC** — Appalachian Regional Commission. Federal agency that classifies counties in the Appalachian region by economic-status tier (Distressed, At-Risk, Transitional, Competitive, Attainment).
- **ArcGIS** — Esri's GIS product family. Many federal / state publishers expose datasets via ArcGIS REST services or hosted ArcGIS Online portals.
- **ASR** — Antenna Structure Registration. The FCC's registry of antenna structures ≥ 200 ft or near airports. Each entry has an ASR registration number, structure coordinates, height, type, status, and registrant entity. Our primary tower-locations source.
- **AutomationPolicy** — Per-source enum on every `DataSource` declaring how the puller may fetch it: `ALLOWED`, `TOLERATED`, `MANUAL_ONLY`, `CREDENTIALED`. See [DATA_SOURCES.md](./DATA_SOURCES.md).

## B

- **Backend** — the FastAPI + SQLAlchemy service alongside the static map app, **live in production**. Holds lead + task state, contact attempts, activity log, scoring presets/settings, owner merge/split overrides; username/password auth ([ADR-062](./adr/0062-username-password-replaces-magic-link.md)/[063](./adr/0063-file-credentials-teams-per-request-authority.md)/[069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)). SQLite-on-volume in prod (Litestream→R2; [ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md)). Lease-doc storage (R2) + Claude API extraction are planned (D+E). See [ADR-055](./adr/0055-hosted-private-backend.md) / [backend/README.md](../backend/README.md).
- **BLM / BIA** — Bureau of Land Management / Bureau of Indian Affairs. Federal landholders whose parcels may not appear in county-level tax rolls.

## C

- **Cadastral** — relating to legal land boundaries / parcels. "MT Cadastral" = Montana's statewide parcel layer.
- **CAMA** — Computer Assisted Mass Appraisal. The county tax-assessor's parcel-attribute database; the upstream of NC OneMap and similar state-aggregated parcel feeds.
- **Canonical type** — a project-internal schema (e.g., `parcel`, `tower`, `distress_overlay`, `lead`, `lease`) that every Normalizer maps its raw data into. See `scripts/preprocess/base.py`.
- **Carrier** — the wireless service (AT&T, Verizon, T-Mobile, Dish) that leases antenna space *from the Vendor*. Sourced from FCC ULS by joining licenses to ASR locations. Not the tower owner — see **Vendor**.
- **Catalog** — the per-state `catalog.json` written by the Composer describing every layer + view available for that state. The map app reads this to populate the UI.
- **CDFI** — Community Development Financial Institution. Treasury designation; CDFI Investment Areas are a distress overlay.
- **Composer** — `scripts/preprocess/compose.py`. For one state FIPS: loads canonical data, runs Joins in dependency order, runs Views, writes per-state outputs + `catalog.json` + `summary.json`.
- **Composite** — the per-state output produced by the Composer. Lives at `data/processed/composite/<fips>/`.

## D

- **Distress overlay** — canonical type for spatial-polygon distress designations (HUD OZ, HUD QCT, ARC counties, USDA persistent poverty). Used to tag parcels with `in_oz`, `in_qct`, `distress_tier`, `persistent_poverty`.
- **DMS** — Degrees / Minutes / Seconds. The coordinate format FCC ASR uses; we convert to decimal degrees during normalize.
- **DSL** — Department of State Lands (Florida). Publishes a parcel layer of *state-owned* land — **not** the FDOR NAL tax-roll layer we actually want. See ADR-019.

## E

- **EIA** — U.S. Energy Information Administration. Publishes Form 860 (annual) + 860M (monthly) — utility-scale power-plant inventories with plant location, owner, capacity.
- **Entity (FCC ASR)** — the registrant / owner of an antenna structure as recorded in `EN.dat` of the ASR bulk data. Not the *landowner* under the tower; that's a separate join. See **Registrant**.
- **EPSG** — coordinate reference system codes from the European Petroleum Survey Group. EPSG:4326 = WGS84 lat/lon (web standard). EPSG:2264 = NC State Plane (ftUS).

## F

- **FAA OEAAA** — FAA Obstruction Evaluation / Airport Airspace Analysis. Pre- and recently-built tall-structure records; forward-looking pipeline of towers.
- **FCC** — Federal Communications Commission. Publishes ASR (tower registrations) and ULS (radio-service licenses).
- **FDOR** — Florida Department of Revenue. Publishes the NAL tax-roll dataset per county.
- **FDOT** — Florida Department of Transportation. Publishes outdoor advertising (billboard) permits.
- **FGDL** — Florida Geographic Data Library. Aggregates various FL state datasets; published DSL (state-land) parcels, **not** FDOR NAL.
- **FIPS** — Federal Information Processing Standards. We use the state FIPS (e.g., `37` = NC, `05` = AR) and county FIPS (e.g., `075` for Graham in NC, full GEOID `37075`).
- **Freestanding tower** — standalone antenna structure (monopole, lattice, guyed) ≥ 200 ft or near an airport, registered in FCC ASR. **Phase 1 primary asset.** Distinct from **Rooftop installation**. See `CONTEXT.md` + [ADR-054](./adr/0054-asset-universe-phase-1-2.md).

## G

- **GeoJSON** — RFC 7946 JSON-based geometry format. What our map app reads for catalog + view layers. Large-row layers are skipped per ADR-052; parcels render from PMTiles.
- **GeoParquet** — Apache Parquet with a standard geometry column encoding. Our canonical analytical format. ~5–10× smaller than GeoJSON, supports column projection.

## H

- **HIFLD** — Homeland Infrastructure Foundation-Level Data. DHS-curated infrastructure datasets. **Retired** the public cellular-towers layer in 2024 (ADR-015).
- **HUD** — U.S. Department of Housing and Urban Development. Publishes OZ (Opportunity Zones), QCT (Qualified Census Tracts).

## I

- **Interestingness score** — composite per-tower / per-parcel score in [0, 1] used for outreach prioritization. Components: infrastructure presence, distress overlap, owner kind (LLCs / trusts weighted), cluster size. Implementation: `scripts/preprocess/scoring.py`. **Tunable + transparent** (Slice C, **shipped** — [ADR-058](./adr/0058-tunable-transparent-scoring.md)) — components stored in parquet, weights set client-side via UI sliders, scoring **presets** persisted (tenant-shared); per-tower scoring landed with owners-index schema v5.

## J

- **Join** — `scripts/preprocess/joins/<name>.py`. Mutates one canonical layer with attributes from another (e.g., `TowerToParcelJoin` adds `parcel_id` to towers). Runs in topo order via `ordered_joins()`.

## L

- **LBNL Tracking the Sun** — Lawrence Berkeley National Lab dataset of US rooftop / distributed PV installations. Dropped from active registry (ADR-016).
- **Lead** — the co-founder's outreach unit. **Keyed on the owner cluster (`display_cluster_id`)** ([ADR-056](./adr/0056-lead-equals-owner-cluster.md)), resolved **across all anchor states** — one landowner = one Lead regardless of how many parcels/towers they hold. Carries the **Lead status** ladder (new → researching → contacted → interested → in_business, or uninterested) plus contact info, attempts, and notes. See [`CONTEXT.md`](../CONTEXT.md) for the full Lead / Candidate / Trigger model.
- **Lease** — the carrier-side ground-lease record. Keyed on `(parcel_id, tower_asr_id, carrier_callsign)`. State machine: unknown → pending_upload → uploaded → extracted → verified → superseded. Document storage + LLM-extracted structured fields land here in Slice D+E ([ADR-059](./adr/0059-llm-lease-extraction.md)).
- **Lease extraction** — the Slice D+E pipeline that turns an uploaded lease PDF into structured fields (rent, escalation, expiry, amendment count, parties, …) plus per-field confidence, via the Claude API. Sonnet 4.6 default with an Opus 4.7 retry path for low-confidence leases; prompt caching on. See [ADR-059](./adr/0059-llm-lease-extraction.md). **Design only — unimplemented as of 2026-05-29.**
- **`lease_comp`** — per-area lease-rent benchmark table. Bootstrapped from Steel-in-the-Air free county-level data in Slice D+E; augmented over time by extracted-lease rent from the cofounder's uploads. Powers the "comparables within X-mile radius" feature.
- **libpostal** — native C library for international address normalization. Preferred for the address half of owner-cluster strengthening in Slice D+E. Fall back to pure-Python `usaddress` if dep-management is painful.
- **LLC unmasking** — the (sensitive, expensive) process of resolving the human(s) behind a legal entity. **Narrowed in [ADR-057](./adr/0057-budget-posture-reframed.md):** paid skip-trace + shell-piercing remain permanent non-goals; **free public-records officer disclosure** (Secretary of State business-entity lookups; UCC-1) is in scope for Phase 1 Slice D+E lead-detail panel.

## M

- **Magic-link auth** — passwordless auth via email-delivered one-time links; the original Slice D+E sign-in design ([ADR-055](./adr/0055-hosted-private-backend.md), implemented in #48). **Removed** — replaced by **username/password login** ([ADR-062](./adr/0062-username-password-replaces-magic-link.md), PRD #75).
- **Manifest** — two distinct files in this project:
  - `data/manifest.json` — fetch manifest; what raw data is on disk.
  - `data/processed/preprocess_manifest.json` — preprocess manifest; what's been normalized / composed.
- **MANUAL_ONLY** — AutomationPolicy meaning the puller will not attempt to fetch; user must download manually. The puller provides a step-by-step walkthrough modal.
- **MapLibre GL JS** — open-source WebGL map renderer (fork of Mapbox GL JS pre-license-change). The map app's rendering engine; see `app/ARCHITECTURE.md`.

## N

- **NAL** — Name, Address, Legal. FL DOR's per-county tax-roll dataset; contains private-owner names + assessed values. The data we actually want for FL (ADR-019).
- **NC OneMap** — North Carolina's geospatial data portal. Publishes standardized statewide parcel data sourced from county CAMA exports. The original Graham County pilot used this source.
- **Normalizer** — `scripts/preprocess/normalizers/<source>.py`. Reads one raw source and emits one or more canonical-type Parquet files plus a `quality_report.json`.

## O

- **OE/AAA** — see FAA OEAAA.
- **Owner cluster** — group of parcels sharing the same normalized-owner + normalized-address pair. ID is SHA1 of the concatenation. Surfaced via the `owner_clusters` view and `owner_cluster_size` column on parcels. **Becomes the Lead key in Slice D+E** ([ADR-056](./adr/0056-lead-equals-owner-cluster.md)); ADR-024's algorithm is strengthened then with conservative normalization layers + manual merge/split UI.
- **`owner_cluster_override`** — Slice D+E backend table storing co-founder-issued manual cluster merges/splits: `(tenant_id, source_cluster_id, target_cluster_id)`. Raw cluster IDs stay in parquet; backend computes `display_cluster_id = coalesce(override_target, raw_cluster_id)`.
- **owner_kind** — categorical inferred from owner-name patterns: `llc`, `individual`, `trust`, `corporation`, `gov`, `church`, `partnership`, `school`, `unknown`. Implementation in `scripts/preprocess/cluster.py`.
- **OZ** — Opportunity Zone. Census tract designated under the 2017 Tax Cuts and Jobs Act; the original "OZ 1.0" designations are in effect through ~2028. "OZ 2.0" redesignations are being made by governors during 2026 — the layer will change.

## P

- **Parcel** — single legally-defined unit of real estate with a unique APN, polygon boundary, owner, mailing address, assessed value. Atomic geographic unit linking infrastructure to a human/entity. Not the same as a **Lead** (which is the owner-cluster).
- **Persistent poverty** — USDA designation for counties with ≥ 20% poverty rate sustained over the past ~30 years.
- **Phase 1** — the current cut. Co-founder-facing product across the committed anchors AR + MT + FL + WV (NC a deferred Phase-1 stretch), freestanding towers only. Slices F → A → C → D+E → B. See [SCOPE.md](./SCOPE.md), [ADR-053](./adr/0053-product-phase-shift.md).
- **Phase 2** — post-Phase-1 expansion. Rooftop installations + mass email + paid Steel-in-the-Air tier + self-serve refresh + recorded-lease automation. See [ROADMAP.md](./ROADMAP.md).
- **PII** — Personally Identifiable Information. Parcel-owner names + mailing addresses meet most PII definitions even when individually public-record. See ADR-040 + [SECURITY.md](./SECURITY.md).
- **PMTiles** — single-file format for vector tiles. HTTP Range-request friendly; no tile server needed. Used for the parcel base layer in the map app.
- **Puller** — the data TUI (`scripts/data_tui/`, `python -m data_tui`): Textual terminal app for pulling raw data into `data/raw/` and driving preprocess → verify → deploy (PRD #233). Replaced the retired PySide6 desktop app (#240). See [PULLER_UX.md](./PULLER_UX.md).
- **Pyogrio** — fast geopandas-compatible reader/writer for vector spatial files (shapefile, GDB, GeoJSON). Used in preprocess.

## Q

- **QCT** — Qualified Census Tract. HUD designation for high-poverty / low-income tracts; one of our distress overlays.

## R

- **Registrant** — the entity listed on FCC ASR `EN.dat` — the party that *registered* the structure with FCC. Often the original builder; frequently sold since. Distinct from the *current* tower owner — see **Vendor**.
- **Regrid** — paid nationwide standardized parcel + owner data service. Phase 2+ unlock per [ADR-057](./adr/0057-budget-posture-reframed.md) (revises ADR-012's "out of scope" framing to "deferred"). Stub source preserved.
- **Rooftop installation** — antenna or DAS installation on a commercial building. Usually under the 200 ft FCC ASR threshold so largely *absent* from ASR. Different data foundation (building cap rate, tenant mix, mortgage — mostly paid). Out of scope for Phase 1; deferred to Phase 2 ([ADR-054](./adr/0054-asset-universe-phase-1-2.md)).

## S

- **safe_merge** — helper in `scripts/preprocess/base.py` that drops pre-existing target columns before a pandas merge, preventing `_x` / `_y` column collisions when a Join adds columns that Normalizers initialize. See ADR-020.
- **SCOPE** — see [SCOPE.md](./SCOPE.md). The locked definition of what's in / out of the current cut.
- **Schema version** — integer field stamped on every canonical output (`_schema_version`). Bumps when the canonical-type schema changes.
- **Scoring profile** — a saved set of client-side interestingness-score weights. Under the tunable/transparent scoring model the score components are stored in parquet and the weights are set via UI sliders; a scoring profile persists a chosen weighting so the co-founder can switch between prioritization lenses. See [ADR-058](./adr/0058-tunable-transparent-scoring.md) and **Interestingness score**.
- **Skip-trace** — paid contact-data resolution (phone, email, current address) via third-party vendors (Whitepages Pro, Cole Information, IDI, Pipl). Permanent non-goal for Phase 1 per [ADR-057](./adr/0057-budget-posture-reframed.md) (narrowing ADR-041). Phase 2 unlock conversation.
- **Slice** — one unit of Phase 1 work with its own "shipped" gate. Phase 1 slices in order: **F** (committed-anchor composes AR+MT+FL+WV; NC deferred), **A** (carriers via ULS), **C** (asset enrichment + tunable scoring UI), **D+E** (lease docs + backend + triage state), **B** (vendor inference). See [SCOPE.md §3–§4](./SCOPE.md) for the canonical plan + gates.
- **SoS** — Secretary of State. Each state's SoS publishes business-entity records (LLC formation, officers, registered agent). **In scope for Phase 1 Slice D+E** lead-detail panel as a one-click helper — see [ADR-057](./adr/0057-budget-posture-reframed.md).
- **Spatial join** — assigning attributes from one geographic layer to another based on spatial relationship (typical case: point-in-polygon, "which parcel contains this tower").
- **Steel-in-the-Air** — third-party publisher of cell-tower lease-rent benchmarks. The free county-level tier was the intended `lease_comp` bootstrap, but its existence was **overturned 2026-05-26** (the free dataset doesn't exist — see [STATUS.md §6](./STATUS.md)); the next-best free path is REIT 10-K / ABS rent disclosures. Paid tier is a Phase 2 unlock ([ADR-057](./adr/0057-budget-posture-reframed.md)).

## T

- **Tenant** — in the backend, a tenant is a logical isolation unit; every table has a `tenant_id` column and every route filters by it. **Teams ARE tenants** — each credential/user is bound to exactly one tenant (= team), resolved per request ([ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md)); there is no `tenant_id = 1` stub. The schema is tenant-shaped from Day 1 so a second team (intern / advisor / paid Phase-3 customer) is a row-add, not a refactor ([ADR-055](./adr/0055-hosted-private-backend.md)). Not to be confused with **building tenants** in the rooftop context (deferred to Phase 2).
- **testcontainers-postgres** — opt-in backend test harness that spins a real Postgres in Docker (`PILOT_TEST_TESTCONTAINERS=1`) to catch Postgres-specific bugs (JSON ops, isolation levels). The default is SQLite (behaviorally equivalent for the schema); auto-starting Postgres was dropped as too slow. See [TESTING.md](./TESTING.md).
- **TIGER** — Topologically Integrated Geographic Encoding and Referencing. Census Bureau's geospatial reference files.
- **Tippecanoe** — Mapbox/Felt CLI tool for generating vector tiles (MBTiles / PMTiles) from large GeoJSON / NDJSON inputs. Required for the map app's parcel base layer.
- **TPO** — Third-Party Ownership (of a solar system). Solar installations under PPA / lease where the contract can potentially be renegotiated. Solar-side concept; renewable-energy analogue of ground leases.
- **Triage** — the co-founder's working session inside the product — filter parcels/towers across anchor states, rank by interestingness, drill into a **Lead**, advance its **Lead status** (new → researching → contacted → interested → in_business / uninterested), log activity, and export. The product's primary user-flow. Distinct from **Outreach** (Phase 2 — the actual email / call layer). See [`CONTEXT.md`](../CONTEXT.md).

## U

- **UCC-1** — Uniform Commercial Code financing statement; secured parties file these. Surfaced in the Slice D+E lead-detail panel as third-party-ownership clues for parcel-attached assets.
- **ULS** — Universal Licensing System (FCC). Six bulk data bands + meta. **Cellular (Part 22) + PCS (Part 24) + AWS / 700 MHz (Part 27) are in Phase 1 Slice A** for carrier identification ([ADR-053](./adr/0053-product-phase-shift.md) partially reverses ADR-013). Microwave, Ownership, Transfers, Leasing remain deferred.
- **USDA ERS** — USDA Economic Research Service. Publishes persistent-poverty + county typology data.
- **Username/password login** — the backend's sign-in front door: credentials in the app DB's `credential` table (PBKDF2 hashes, managed via `python -m app.users`), exchanged at `POST /api/auth/login` for an identity-only HS256 session JWT set in an httpOnly cookie; the credential table re-authorizes every request ([ADR-062](./adr/0062-username-password-replaces-magic-link.md) / [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md) / [ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md), PRDs #75 / #83 / #130). Replaced magic-link auth. Mechanics: [backend/README.md](../backend/README.md).
- **USPVDB** — US Photovoltaic Database. USGS / Berkeley dataset of utility-scale solar facility polygons.
- **usaddress** — pure-Python US-only address parser. Fallback if libpostal install is painful in Slice D+E. Narrower coverage, no native dependencies.

## V

- **Vendor** — the tower-co that *currently* owns the antenna structure and collects rent from carriers (Crown Castle, American Tower / ATC, SBA, Vertical Bridge). Not directly recorded in any free dataset; inferred from FCC ASR Registrant for un-sold towers (Slice B) or from recorded-lease lessee names for sold towers (Phase 2). Not the wireless service — see **Carrier**.
- **View** — `scripts/preprocess/views/<name>.py`. Derived dataset built on top of composed canonical data (e.g., `llc_owned_parcels_with_infra`, `interestingness_top_1000`). Surfaced in the catalog and as map filter toggles.

## W

- **WGS84** — the lat/lon coordinate system used by GPS and web mapping. EPSG:4326. All our output is in this CRS.
