# Changelog

The newest-first record of what shipped when. [STATUS.md](./STATUS.md) describes where the
project stopped; this doc keeps the trail. Finer detail lives in git.

For why each decision was made, see the ADRs ([DECISIONS.md](./DECISIONS.md)).

---

## Archive (2026-10)

- **2026-10-18: public read-only demo (ADR-077).** The `credential` table gained a
  `read_only` flag, enforced in one place. `current_principal` refuses a read-only
  principal's writes with 403. `DEMO_MODE` adds a password-less "Explore the demo" sign-in
  (`POST /api/auth/demo`) for the one credential named by `DEMO_USERNAME`, and boot refuses
  unless that credential exists and is read-only. `python -m app.demo_seed` creates it and
  seeds six fictional leads over business-entity owners; supervisord runs the seed before
  uvicorn when `DEMO_MODE` is on. The SPA shows a "Read-only demo" badge, hides write
  controls, and raises one notice if a 403 still gets through. Deployed as `morphy-demo`.
- **2026-10: archived and prepared for public release.** The data-audit site and the Ask
  Claude helper were removed, along with the `ask_log` table (Alembic
  `0003_read_only_credential_drop_ask_log`). The project was renamed from pilot to morphy,
  including the session cookie (now `morphy_session`). The MapTiler key moved into a
  git-ignored `.env`, with a keyless basemap fallback. An MIT license was added.

---

## Phase 1: the product cut (2026-05-25 to 2026-07)

### 2026-07: data TUI, auto-fetch flips, Qt puller retired

- **2026-07-03: registry cleanup, HIFLD removed, FL FGDL DSL re-activated.** The dead
  `hifld_towers` source (Homeland Infrastructure Foundation-Level Data, retired upstream
  by the Department of Homeland Security in 2024, ADR-015) was deleted outright.
  `fl_fgdl_parcels`, the Florida Geographic Data Library (FGDL) composite of
  *state-owned land* from the Division of State Lands (DSL), holds about 241K parcels in
  the FL composite. It was recognized as a complement to the Florida Department of
  Revenue (FDOR) Name-Address-Legal (NAL) parcels rather than superseded dead weight. It
  moved to the active registry and flipped to auto-fetch (direct download; the fetcher
  discovers the newest release filename from the FGDL listing). 16 of 17 active sources
  auto-fetched; AR remained the only manual source.
- **2026-07-03: data TUI shipped; Qt puller retired.** The "puller no longer works"
  report traced back to the FCC bot filter stalling urllib requests that lacked a
  browser-like `Accept-Encoding` header (fixed in `fetch/http.py`). After a per-source
  terms review, MT, WV and FL FDOR parcels flipped from MANUAL_ONLY to auto (15 of 16
  active sources auto-fetched; AR stayed manual). The **Textual data TUI**
  (`scripts/data_tui/`, `python -m data_tui`) shipped covering the full lifecycle: pull
  (background jobs, progress, resume, desktop notifications, structured failure detail
  via manifest schema v3 `last_error`) → preprocess (pure refresh planner,
  affected-state preselection) → composite verify (against the last deploy receipt) →
  confirm-gated `deploy.sh data` plus smoke. A data-freshness read-out for the user
  shipped in the app at the same time. With the successor tested, the **Qt puller and
  its PySide6 pin were deleted**, as its retirement plan required (ADR-007 retired).

### 2026-06: internal tooling, Ask Claude, hardening, Halo re-skin

- **2026-06-25/27: data-audit fixes, basemap, county FIPS fix.** All 14 easy-bucket
  data-audit fixes landed. The MapTiler Satellite Hybrid basemap became the app default.
  A malformed-`CENSUS_BK` bug that produced cross-state county Federal Information
  Processing Standards (FIPS) codes was fixed in preprocess.
- **2026-06-23/24: "Halo" dark design system.** The map app and the data-audit site were
  re-skinned onto one dark theme, and the light/dark chrome toggle was retired (the map
  basemap picker stayed). The Dashboard moved to a 2×2 digest grid.
- **2026-06-20: data-audit catalog and Ask Claude shipped.** A standalone Svelte app
  served a browsable data catalog over the data-audit working files, behind the same
  `forward_auth` gate as `/data/processed/*`. **Ask Claude** was an in-catalog LLM helper
  and the backend's first server-sent events stream: `POST /api/audit/ask` plus an
  `ask_log` table (Alembic `0002_ask_log`). It stayed dormant until an
  `ANTHROPIC_API_KEY` secret was set and returned a clean 503 in the meantime. Both were
  removed when the project was archived.
- **2026-06-21: dead-code removal sweep.** Retired the verified-dead parcel-grained
  filter subsystem, plus small backend and preprocess cuts.
- **2026-06-12/13: Phase 1 hardening (all shipped 2026-06-13).** Closed the
  unauthenticated personally identifiable information (PII) data plane, moved
  credentials into the app DB, and switched to cookie sessions (ADR-069). Also: a
  frontend CI gate; the uv toolchain with real packaging, retiring the `sys.path` hacks;
  generated OpenAPI→TS types with a drift gate; Alembic versioned migrations; DuckDB as
  the preprocess heavy-lift engine; pyright on `backend/`; cross-language contract
  fixtures; and the Qt puller frozen to bug fixes only, with a named Textual TUI
  successor.

### 2026-06-04/07: production deploy and UI overhaul

- **Deployed.** The app went live on a single always-on Fly machine with
  SQLite-on-volume, Litestream→R2 backups and a Cloudflare front (ADR-064). DuckDB-WASM
  and PMTiles were served client-side over HTTP Range. `deploy.sh smoke` asserted that
  unauthenticated `/data/processed/*` requests got 401/403.
- **UI overhaul and Settings (ADR-065/066/067/068).** A three-section information
  architecture (Dashboard · Explore · Leads) with a Dashboard digest hub; the Tasks
  subsystem (`task` table, `/api/tasks`, automatic follow-ups); tower-grained Explore
  with a per-tower `score` (owners index → **schema v5**); an inbound-reply activity
  seam (`ContactAttempt.direction`); per-user Settings (theme, colorblind mode, basemap,
  default view, filter defaults) and self-service password change.

### 2026-05-30/06-02: auth, lead-centric redesign, carriers

- **Auth (ADR-062/063).** Username/password sign-in replaced magic links. Teams became
  tenants, the credential source re-authorized every request, and the JWT carried
  identity only. (Credential storage later moved to the DB, ADR-069.)
- **Lead-centric triage redesign complete (ADR-061).** Built in slices: write-layer
  tracer → auth → full Lead page (owners index v2) → structures-first map → My Leads
  kanban → top-bar filters and owner/Antenna Structure Registration (ASR) search (v3) →
  manual owner merge/split.
- **Slice A: carrier identification landed.** The FCC Universal Licensing System
  (ULS)↔ASR carrier layer plus the carrier-list UI (owners index → v4 `carriers`).
  Coverage was about 6-17% of ASR towers (high precision, low recall), so an empty list
  was the common case.
- **Slice C: tunable scoring UI shipped**, with live re-rank and named presets.
  Solar→parcel was done; billboards stayed a no-op because anchor raw data was never
  populated.

### 2026-05-29: West Virginia anchor and FL recompose

- **WV added and made a committed anchor (ADR-060).** A new `wv_parcels` MANUAL_ONLY
  source (the WV GIS Technical Center statewide `.gdb`, published under Senate Bill 588);
  `composite/54` built with 1,389,855 parcels, 11 joins, 8 views and 0 warnings. The
  committed set became **AR + MT + FL + WV**.
- **FL recomposed (county-score gap closed).** `composite/12` was rebuilt via chunked
  compose (11,425,608 parcels, 11 joins, 8 views, 0 warnings). The `county_scores` layer
  and the tower/solar county-score joins became present, consistent with AR and MT.

### 2026-05-25: phase shift from demo to Phase 1 product (ADR-053)

The project reframed from a demo across 4 states to Phase 1 of an analyst-facing product.
Feature areas that had been deferred came into scope: FCC ULS carriers, billboards and
solar on parcel, lease-document upload with LLM extraction, the triage write layer, and
free public-records contact enrichment. The slice plan F → A → C → D+E → B and the
outcome bar were set here. Superseded or narrowed ADRs: 006→055, 010→057 (reframed),
041→057 (narrowed). See [STATUS.md](./STATUS.md).

---

## Before the phase shift: demo foundation

### v3: demo foundation (May 2026, partial)

An eight-section production-readiness plan aimed at a demo across 4 anchor states. The
framework, the puller, Git and CI, the map-app rebuild (Svelte 5 + MapLibre + PMTiles +
DuckDB-WASM at `app/`), and the AR/MT data-quality fixes all shipped. Sections 6
(testing) and 7 (demo readiness) did not ship before the 2026-05-25 phase shift.

### v2: preprocess framework

Registry-driven preprocessing replaced the one-shot script: a `Normalizer` per source, a
`Join` per cross-source relationship, a `View` per derived dataset, a per-state
`Composer`, dual GeoParquet + GeoJSON output (modulo `NO_GEOJSON_THRESHOLD`, ADR-052),
canonical schemas (`parcel`/`tower`/`distress_overlay`/`solar_facility`/`billboard`/`county_score`),
owner clustering (ADR-024), and interestingness scoring (ADR-058).

### v1: data puller

A PySide6 desktop app at `app_puller/` for pulling raw data sources into
`data/raw/<source_id>/current/`. Per-source `AutomationPolicy`; atomic `.partial → current/`
promotion; a single `data/manifest.json`; a JSONL fetch log. (Later frozen, then deleted
once the data TUI replaced it.)

### v0: Graham County one-shot (early prototype)

A single `preprocess.py` script that ingested FCC ASR, NC OneMap parcels for Graham County
and HUD Opportunity Zones, spatial-joined them, and produced three GeoJSON files for a
Leaflet web map. It proved the tower → parcel → distress linkage but was hard-coded to one
county. The one-shot script and its plan were retired (recover from git:
`git log --all -- docs/archive/`).
