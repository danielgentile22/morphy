# Decisions (index)

This is the index of the project's architecture decision records (ADRs); each one lives as its own file under [`docs/adr/`](./adr/).

---

## Active

Decisions still in force when the project was archived.

### Foundation

| # | Title |
|---|---|
| [ADR-001](./adr/0001-state-level-geographic-scope.md) | State-level geographic scope |
| [ADR-002](./adr/0002-registry-driven-architecture.md) | Registry-driven Normalizer / Join / View architecture |
| [ADR-004](./adr/0004-current-only-versioning.md) | Current-only data versioning, no history |
| [ADR-005](./adr/0005-on-demand-fetch-only.md) | On-demand fetch trigger only |
| [ADR-042](./adr/0042-docs-in-subfolder.md) | Documentation lives in `docs/` |
| [ADR-044](./adr/0044-ci-github-actions.md) | CI on GitHub Actions |
| [ADR-045](./adr/0045-registry-active-deferred.md) | Registry split into `_ACTIVE` / `_DEFERRED` blocks |

### Data sourcing

| # | Title |
|---|---|
| [ADR-012](./adr/0012-regrid-deferred.md) | Regrid deferred (paid) |
| [ADR-015](./adr/0015-hifld-towers-retired.md) | HIFLD towers retired |
| [ADR-016](./adr/0016-lbnl-tts-dropped.md) | LBNL Tracking the Sun dropped |
| [ADR-017](./adr/0017-indiana-dropped.md) | Indiana dropped (no owner data) |
| [ADR-018](./adr/0018-minnesota-deferred.md) | Minnesota deferred (license ambiguity) |
| [ADR-047](./adr/0047-fdor-nal-67-counties.md) | FL FDOR NAL expanded to all 67 counties |
| [ADR-048](./adr/0048-nc-onemap-mapserver-pagination.md) | NC OneMap parcels via MapServer pagination |
| [ADR-049](./adr/0049-utah-dropped.md) | Utah dropped (no owner data) |

### Code architecture

| # | Title |
|---|---|
| [ADR-020](./adr/0020-safe-merge-helper.md) | `safe_merge` helper for column-aware joins |
| [ADR-021](./adr/0021-source-flag.md) | `--source` flag for selective rebuild |
| [ADR-022](./adr/0022-rebuild-manifest.md) | `--rebuild-manifest` for disk-derived sync |
| [ADR-050](./adr/0050-streaming-per-county-normalize.md) | Streaming per-county parcel normalize |
| [ADR-052](./adr/0052-no-geojson-threshold.md) | `NO_GEOJSON_THRESHOLD`: Parquet-only for very large layers |

### Policy

| # | Title |
|---|---|
| [ADR-040](./adr/0040-parcel-owner-pii.md) | Parcel-owner data is personally identifiable information (PII) |

### Phase 1 product cut (2026-05-25)

| # | Title |
|---|---|
| [ADR-053](./adr/0053-product-phase-shift.md) | Product phase shift from demo to daily-use product |
| [ADR-054](./adr/0054-asset-universe-phase-1-2.md) | Phase 1 freestanding / Phase 2 rooftops |
| [ADR-055](./adr/0055-hosted-private-backend.md) | Hosted-private backend (Slice 4) |
| [ADR-056](./adr/0056-lead-equals-owner-cluster.md) | Lead = owner-cluster |
| [ADR-057](./adr/0057-budget-posture-reframed.md) | Budget posture reframed |
| [ADR-058](./adr/0058-tunable-transparent-scoring.md) | Tunable + transparent scoring |
| [ADR-059](./adr/0059-llm-lease-extraction.md) | LLM extraction approach for leases |
| [ADR-060](./adr/0060-wv-committed-anchor.md) | West Virginia elevated to a committed Phase 1 anchor |
| [ADR-061](./adr/0061-lead-centric-triage-redesign.md) | Lead-centric triage UI redesign: cross-state leads, structures-first map, write layer pulled forward |
| [ADR-062](./adr/0062-username-password-replaces-magic-link.md) | Username/password login replaces magic-link; magic-link machinery removed |
| [ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md) | Phase 1 hosting on one always-on Fly.io machine, SQLite on a volume, Cloudflare in front (~$5-8/mo) |

### Phase 1 UI overhaul (2026-06-06)

| # | Title |
|---|---|
| [ADR-065](./adr/0065-redesign-three-section-ia.md) | Redesigned app information architecture: three sections (Dashboard · Explore · Leads) and a Dashboard digest hub |
| [ADR-066](./adr/0066-inbound-event-reply-seam.md) | Replies are provider-agnostic inbound activity events (manual entry, Gmail planned but never built) |
| [ADR-067](./adr/0067-tower-grained-explore.md) | Tower-grained Explore + per-tower scoring; owner stays the unit of work (extends ADR-061) |
| [ADR-068](./adr/0068-self-service-password-change.md) | Self-service password change is a sanctioned runtime caller of the credentials writer (the Settings page; re-homed onto the DB store by ADR-069) |

ADR-058 (tunable scoring) was amended the same day to add tower grain, "preset" terminology and tenant-shared storage. Its row stays under *Phase 1 product cut*.

### Phase 1 hardening (2026-06-12)

| # | Title |
|---|---|
| [ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md) | Credentials move to the app DB; httpOnly-cookie sessions; `/data/processed/*` gated at the edge via `forward_auth` (amends ADR-063's storage; its authority invariants stand) |

### Data-audit follow-through (2026-07-03)

Seven decisions from a 2026-06 data audit, whose working files are not part of this repo. Each ADR's status line records how far its implementation got.

| # | Title |
|---|---|
| [ADR-070](./adr/0070-statutory-assessed-value.md) | Surface statutory assessed value alongside market/appraised value |
| [ADR-071](./adr/0071-solar-feed-dedup.md) | Solar feed dedup, with EIA-860 as the base of record |
| [ADR-072](./adr/0072-faa-asr-corroboration.md) | FAA↔ASR co-location match dedups the towers layer |
| [ADR-073](./adr/0073-interestingness-reweight.md) | Reweight interestingness → small-portfolio / low-value / high-carrier (amends ADR-058) |
| [ADR-074](./adr/0074-uls-carrier-rearchitecture.md) | Rearchitect ULS→carrier: all modern spectrum, authorization-not-tenancy semantics |
| [ADR-075](./adr/0075-cross-state-owner-identity.md) | Cross-state owner identity: name+state key + curated multi-state alias table |
| [ADR-076](./adr/0076-owner-type-classifier.md) | Owner-type classifier: expanded regex first, LLM for the ambiguous residual |

### Public demo (2026-10-18)

| # | Title |
|---|---|
| [ADR-077](./adr/0077-read-only-demo-credential.md) | A read-only demo credential behind DEMO_MODE; Ask Claude retired |
| [ADR-078](./adr/0078-demo-leads-over-government-owners.md) | Demo leads sit on government owners only |

---

## Realized

Locked, then shipped.

| # | Title | Shipped |
|---|---|---|
| [ADR-030](./adr/0030-map-app-v2-stack.md) | Map app v2 stack: MapLibre + PMTiles + DuckDB-WASM + Svelte | 2026-05-21 (`app/`) |
| [ADR-043](./adr/0043-tests-pytest-vitest-playwright.md) | pytest + Vitest + Playwright test stack | 2026-05-21 (`tests/`, `app/tests/`) |
| [ADR-051](./adr/0051-chunked-compose.md) | Chunked compose for memory-bounded large states | 2026-05-19 (single-shot retired 2026-05-27) |

---

## Revised, narrowed or partially reversed

Earlier decisions still partly in force, modified by a later ADR.

| # | Title | Modified by |
|---|---|---|
| [ADR-003](./adr/0003-dual-geoparquet-geojson.md) | Dual GeoParquet + GeoJSON output | Narrowed by [ADR-052](./adr/0052-no-geojson-threshold.md) (Parquet-only above 250K rows) |
| [ADR-010](./adr/0010-free-only-budget.md) | Strict free-only data budget | Revised by [ADR-057](./adr/0057-budget-posture-reframed.md) from "permanent" to "the Phase 1 posture" |
| [ADR-011](./adr/0011-anchor-states.md) | Anchor states AR + NC + MT + UT (+ FL stretch) | UT dropped by [ADR-049](./adr/0049-utah-dropped.md); committed set re-cut to **AR + MT + FL + WV** by [ADR-060](./adr/0060-wv-committed-anchor.md) (WV added, NC demoted to a deferred stretch) |
| [ADR-013](./adr/0013-fcc-uls-deferred.md) | FCC ULS normalizers deferred | Partially reversed by [ADR-053](./adr/0053-product-phase-shift.md) Slice A, which brought Cellular/PCS/AWS/700 MHz back in |
| [ADR-014](./adr/0014-billboards-deferred.md) | Billboards deferred | Partially reversed by [ADR-053](./adr/0053-product-phase-shift.md) Slice C, which brought billboards back as parcel enrichment |
| [ADR-023](./adr/0023-huge-geojson-threshold.md) | `HUGE_GEOJSON_THRESHOLD = 100,000` | Narrowed by [ADR-052](./adr/0052-no-geojson-threshold.md) (250K hard ceiling above this) |
| [ADR-024](./adr/0024-owner-clustering-sha1.md) | Owner clustering = SHA1(normalized name + address) | Follow-up locked in [ADR-056](./adr/0056-lead-equals-owner-cluster.md): conservative normalization layers + manual merge/split UI before SHA1 |
| [ADR-041](./adr/0041-no-llc-unmasking.md) | No LLC unmasking | Narrowed by [ADR-057](./adr/0057-budget-posture-reframed.md): free Secretary of State officer disclosure in scope; paid skip-trace stays a non-goal |
| [ADR-055](./adr/0055-hosted-private-backend.md) | Hosted-private backend (Slice 4) | Magic-link auth portion superseded by [ADR-062](./adr/0062-username-password-replaces-magic-link.md) (username/password login); platform, managed-Postgres and S3-service portions narrowed by [ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md) (Fly.io + SQLite on a volume + R2); the backend and day-one `tenant_id` decision stands |
| [ADR-058](./adr/0058-tunable-transparent-scoring.md) | Tunable + transparent interestingness scoring | Default weights + owner rollup reweighted by [ADR-073](./adr/0073-interestingness-reweight.md) (small-portfolio / low-value / high-carrier); the tunable/transparent framework stands |
| [ADR-062](./adr/0062-username-password-replaces-magic-link.md) | Username/password login replaces magic-link | Credential store (`APP_USERS` env) and the "no server-side revocation" trade-off superseded by [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md); the username/password front door, throttle and fail-closed posture stand |
| [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md) | File-based credentials (users.txt + CLI), teams-as-tenants, per-request file authority | **Storage superseded** by [ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md) (credentials in the app DB). The authority model (per-request authority, identity-only JWT, teams-as-tenants, fail-closed posture, CLI-only writes) stands unchanged |

---

## Superseded

Replaced wholesale by a later ADR.

| # | Title | Superseded by |
|---|---|---|
| [ADR-006](./adr/0006-static-site-no-backend.md) | Static-site, no backend | [ADR-055](./adr/0055-hosted-private-backend.md) for write-layer features (reads stay static) |
| [ADR-007](./adr/0007-pyside6-pinned.md) | PySide6 pinned at 6.7.3 | Retired 2026-07-03. The pinned dependency left the tree when the Qt puller was deleted; the puller became the Textual data TUI |
| [ADR-019](./adr/0019-fl-fgdl-to-fdor-nal.md) | FL FGDL DSL → `fdor_nal` source | [ADR-047](./adr/0047-fdor-nal-67-counties.md) (county scope) |
| [ADR-031](./adr/0031-map-rehaul-deferred.md) | Map app rehaul deferred past the first cut | [ADR-030](./adr/0030-map-app-v2-stack.md) (the rehaul happened in the same cut) |
| [ADR-046](./adr/0046-fl-fdor-nal-10-counties.md) | FL FDOR NAL: 10 representative counties | [ADR-047](./adr/0047-fdor-nal-67-counties.md) (expanded to all 67) |

---

## Conventions

- **Numbering** is sparse. The gaps (008/009, 025-029, 032-039) are intentional; numbers were never reused.
- **Status lines** at the top of each ADR file state whether the decision held. This index is for navigation; the ADR file is the source of truth.
- **Changed decisions** kept their original prose. A "Superseded by ADR-X" or "Revised by ADR-X" status line records what changed.
