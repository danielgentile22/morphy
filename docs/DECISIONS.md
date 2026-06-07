# DECISIONS — Architecture Decision Records (index)

**Last updated:** 2026-06-06 (ADR-065/066/067 — UI overhaul: three-section IA + Dashboard digest-hub, inbound-event reply seam, tower-grained Explore; ADR-058 amended for tower-grain scoring presets)

Index of every locked-in design choice in the repo. Per-ADR content lives under [`docs/adr/`](./adr/). New ADRs go straight there ([CLAUDE.md §9](../CLAUDE.md)).

> When in doubt about a design call, open the ADR before reopening the debate. If the entry is here, the decision is locked unless the *context* materially changes.

---

## Active

The currently-binding decisions.

### Foundation

| # | Title |
|---|---|
| [ADR-001](./adr/0001-state-level-geographic-scope.md) | State-level geographic scope |
| [ADR-002](./adr/0002-registry-driven-architecture.md) | Registry-driven Normalizer / Join / View architecture |
| [ADR-004](./adr/0004-current-only-versioning.md) | Current-only data versioning, no history |
| [ADR-005](./adr/0005-on-demand-fetch-only.md) | On-demand fetch trigger only |
| [ADR-007](./adr/0007-pyside6-pinned.md) | PySide6 pinned at 6.7.3 |
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
| [ADR-051](./adr/0051-chunked-compose.md) | Chunked compose for memory-bounded large states |
| [ADR-052](./adr/0052-no-geojson-threshold.md) | `NO_GEOJSON_THRESHOLD`: Parquet-only for very large layers |

### Policy

| # | Title |
|---|---|
| [ADR-040](./adr/0040-parcel-owner-pii.md) | Parcel-owner data is PII |

### Phase 1 product cut (2026-05-25)

| # | Title |
|---|---|
| [ADR-053](./adr/0053-product-phase-shift.md) | Product phase shift — pitch demo → co-founder-facing product |
| [ADR-054](./adr/0054-asset-universe-phase-1-2.md) | Phase 1 freestanding / Phase 2 rooftops |
| [ADR-055](./adr/0055-hosted-private-backend.md) | Hosted-private backend (Slice 4) |
| [ADR-056](./adr/0056-lead-equals-owner-cluster.md) | Lead = owner-cluster |
| [ADR-057](./adr/0057-budget-posture-reframed.md) | Budget posture reframed |
| [ADR-058](./adr/0058-tunable-transparent-scoring.md) | Tunable + transparent scoring |
| [ADR-059](./adr/0059-llm-lease-extraction.md) | LLM extraction approach for leases |
| [ADR-060](./adr/0060-wv-committed-anchor.md) | West Virginia elevated to a committed Phase-1 anchor |
| [ADR-061](./adr/0061-lead-centric-triage-redesign.md) | Lead-centric triage UI redesign — cross-state leads, structures-first map, write-layer pulled forward |
| [ADR-062](./adr/0062-username-password-replaces-magic-link.md) | Username/password login replaces magic-link; magic-link machinery removed |
| [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md) | File-based credentials (users.txt + CLI), teams-as-tenants, per-request file authority |
| [ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md) | Phase-1 hosting — Fly.io single always-on machine, SQLite-on-volume, Cloudflare front (~$5–8/mo) |

### Phase 1 UI overhaul (2026-06-06)

| # | Title |
|---|---|
| [ADR-065](./adr/0065-redesign-three-section-ia.md) | Redesigned app IA — three sections (Dashboard · Explore · Leads) + Dashboard digest-hub |
| [ADR-066](./adr/0066-inbound-event-reply-seam.md) | Replies are provider-agnostic inbound activity events (manual now, Gmail later) |
| [ADR-067](./adr/0067-tower-grained-explore.md) | Tower-grained Explore + per-tower scoring; owner stays the unit of work (extends ADR-061) |
| [ADR-068](./adr/0068-self-service-password-change.md) | Self-service password change is a sanctioned runtime caller of `users.set_password` (PRD #121 Settings page) |

> ADR-058 (tunable scoring) **amended** the same day — tower-grain + "preset" terminology + tenant-shared storage; the row stays under *Phase 1 product cut*.

---

## Realized

Locked, then shipped.

| # | Title | Shipped |
|---|---|---|
| [ADR-030](./adr/0030-map-app-v2-stack.md) | Map app v2 stack: MapLibre + PMTiles + DuckDB-WASM + Svelte | 2026-05-21 (`app/`) |
| [ADR-043](./adr/0043-tests-pytest-vitest-playwright.md) | pytest + Vitest + Playwright test stack | 2026-05-21 (`tests/`, `app/tests/`) |

---

## Revised / Narrowed / Partially reversed

Earlier decisions still partially in force, modified by a later ADR.

| # | Title | Modified by |
|---|---|---|
| [ADR-003](./adr/0003-dual-geoparquet-geojson.md) | Dual GeoParquet + GeoJSON output | Narrowed by [ADR-052](./adr/0052-no-geojson-threshold.md) (parquet-only above 250K rows) |
| [ADR-010](./adr/0010-free-only-budget.md) | Strict free-only data budget | Revised by [ADR-057](./adr/0057-budget-posture-reframed.md) — "permanent" → "current Phase 1 posture" |
| [ADR-011](./adr/0011-anchor-states.md) | Anchor states AR + NC + MT + UT (+ FL stretch) | Superseded UT portion by [ADR-049](./adr/0049-utah-dropped.md) |
| [ADR-013](./adr/0013-fcc-uls-deferred.md) | FCC ULS normalizers deferred | Partially reversed by [ADR-053](./adr/0053-product-phase-shift.md) Slice A — Cellular/PCS/AWS/700 MHz back in |
| [ADR-014](./adr/0014-billboards-deferred.md) | Billboards deferred | Partially reversed by [ADR-053](./adr/0053-product-phase-shift.md) Slice C — billboards return as parcel enrichment |
| [ADR-023](./adr/0023-huge-geojson-threshold.md) | `HUGE_GEOJSON_THRESHOLD = 100,000` | Narrowed by [ADR-052](./adr/0052-no-geojson-threshold.md) (250K hard ceiling above this) |
| [ADR-024](./adr/0024-owner-clustering-sha1.md) | Owner clustering = SHA1(normalized name + address) | Follow-up locked in [ADR-056](./adr/0056-lead-equals-owner-cluster.md) — conservative normalization layers + manual merge/split UI before SHA1 |
| [ADR-041](./adr/0041-no-llc-unmasking.md) | No LLC unmasking | Narrowed by [ADR-057](./adr/0057-budget-posture-reframed.md) — free SoS officer disclosure in scope; paid skip-trace stays non-goal |
| [ADR-055](./adr/0055-hosted-private-backend.md) | Hosted-private backend (Slice 4) | Magic-link auth portion superseded by [ADR-062](./adr/0062-username-password-replaces-magic-link.md) (username/password login); platform + managed-Postgres + S3-service portions narrowed by [ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md) (Fly.io + SQLite-on-volume + R2); the backend + `tenant_id` Day-1 decision stands |
| [ADR-062](./adr/0062-username-password-replaces-magic-link.md) | Username/password login replaces magic-link | Credential store (`APP_USERS` env) + "no server-side revocation" trade-off superseded by [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md); the username/password front door, throttle, and fail-closed posture stand |

---

## Superseded

Replaced wholesale by a later ADR.

| # | Title | Superseded by |
|---|---|---|
| [ADR-006](./adr/0006-static-site-no-backend.md) | Static-site, no backend | [ADR-055](./adr/0055-hosted-private-backend.md) for write-layer features (reads stay static) |
| [ADR-019](./adr/0019-fl-fgdl-to-fdor-nal.md) | FL FGDL DSL → `fdor_nal` source | [ADR-047](./adr/0047-fdor-nal-67-counties.md) (county scope) |
| [ADR-031](./adr/0031-map-rehaul-deferred.md) | Map app rehaul deferred to post-pitch | [ADR-030](./adr/0030-map-app-v2-stack.md) (rehaul was executed in-cut) |
| [ADR-046](./adr/0046-fl-fdor-nal-10-counties.md) | FL FDOR NAL: 10 representative counties | [ADR-047](./adr/0047-fdor-nal-67-counties.md) (expanded to all 67) |

---

## Conventions

- **Numbering** is sparse — gaps (008/009, 025–029, 032–039) are intentional, never reused.
- **Status lines** at the top of each ADR file authoritatively state whether the decision is still binding. This index is the navigation surface; the ADR file is the truth.
- **New ADRs** create a new file under `docs/adr/NNNN-slug.md` and add a row here (in the right section).
- **A decision moves status** by editing the ADR's status line + moving its row in this index. The old prose stays — a "Superseded by ADR-X" header tells future readers what changed.
