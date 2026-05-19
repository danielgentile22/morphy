# Map App Rehaul — Architecture & Phased Plan

> **Status: DEFERRED — revisit post-pitch.**
> **Last updated:** 2026-05-19.
>
> Per [DECISIONS.md ADR-031](./DECISIONS.md), the audit that
> preceded the production-readiness push surfaced bigger gaps
> (broken endpoints, missing normalizers, no tests, doc drift) than
> the map app itself. Sequencing those first gives the rebuild a
> solid foundation.
>
> The current Leaflet app at `app/` gets minimal patches only during
> Section 8 of the production-readiness work plan. This rebuild plan
> stays here as the canonical roadmap for the next push.
>
> When work resumes: open this doc, answer the blockers in Part 4,
> and proceed with Phase 0.

---

A complete rebuild of the Leaflet map app (`app/`) into a vector-tile,
WebGL-rendered, DuckDB-backed analytical app that handles every state's
data — including AR (2.1M parcels) and IN (3.7M parcels) — and scales to
nationwide coverage with no backend.

This document is split into five parts:

1. **Architecture decisions** — every major choice, alternatives debated, lock-in.
2. **Phased plan** — 10 phases with acceptance criteria + tests.
3. **Total timeline** — day estimates per phase.
4. **Blockers / questions** that need user input before kickoff.
5. **What happens after sign-off** — first batch I'd ship.

---

## Part 1 — Architecture decisions

Each decision lists the options I considered, the trade-offs, and the
locked-in choice. The order is roughly load-bearing first (decisions that
constrain everything downstream).

### Decision 1 — Map rendering engine

| Option | Pros | Cons |
|---|---|---|
| **A.** Keep Leaflet, add MapLibre via `maplibre-gl-leaflet` shim | Reuses existing styles; minimal HTML churn | Community shim is unmaintained; coord-system mismatches; click events split across two engines; well-known footgun |
| **B. MapLibre GL JS (native)** | WebGL-accelerated; native vector-tile + PMTiles support; industry standard; 60fps on 5M features | Throws away ~50 lines of Leaflet styling code |
| C. Leaflet.VectorGrid | Pure Leaflet | No WebGL; chokes past ~100K features; project poorly maintained |
| D. Stay GeoJSON-only with server-side subset | Simple | We have no server; defeats the static-site model |

**Locked: B (MapLibre GL JS).** For 3.7M parcels in IN — and the
eventual 100M+ rows when we go nationwide — WebGL is the only realistic
rendering path. The Leaflet styling cost is trivial to port.

### Decision 2 — Tile format

| Option | Pros | Cons |
|---|---|---|
| **A. PMTiles** | Single file; HTTP Range requests; works on any static host (S3, GH Pages, even `python -m http.server`); mature browser library; native tippecanoe output | None for our use case |
| B. MBTiles | Standard | Requires a tile server (martin, tippecanoe-server) — violates the no-backend constraint |
| C. ZXY directory of XYZ tiles | CDN-friendly | Millions of small files; painful to sync / back up |
| D. Static MVT | Works | PMTiles is strictly more functional (PMTiles is "MVT in a single seekable file") |

**Locked: A (PMTiles).** Designed exactly for our deployment model.

### Decision 3 — Tile generation tool

**Locked: `tippecanoe`** with native PMTiles output
(`--output=parcels.pmtiles`, requires tippecanoe ≥ 2.45 from Felt's
fork; Homebrew installs this). Streaming input from parquet via stdin so
we don't OOM on IN's 3.7M rows.

### Decision 4 — Frontend framework

| Option | Bundle | Reactivity | Learning curve | Verdict |
|---|---|---|---|---|
| A. Vanilla JS (current) | 0 KB | Manual | None | Already creaky; will become spaghetti with 10+ filters + top-N list + multi-layer state |
| B. Vue 3 | ~40 KB | Reactive proxy | Low | Solid, but Svelte is faster and smaller |
| **C. Svelte + Vite** | ~3 KB runtime | Compile-time | Low (closer to HTML than React) | Best runtime perf; smallest bundle; cleanest reactivity; fastest dev server |
| D. Preact | ~3 KB | React API | Low if you know React | No clear win over Svelte; we don't need JSX |
| E. React + Vite | ~45 KB | Virtual DOM | Medium | Overkill; slower; bigger |

**Locked: Svelte 4 + Vite + TypeScript.** Smallest runtime matters when
we're juggling 3.7M-row filtering. TypeScript adds compile-time safety
aligned with the "reliability" priority. Build output is static —
`python -m http.server` still serves it.

**Counter-debate considered:** staying vanilla preserves zero build
steps. Rejected because the bespoke event-wiring layer becomes the new
fragility — wrong place to optimize.

### Decision 5 — Filter / query engine

| Option | Bundle | Scale ceiling | Verdict |
|---|---|---|---|
| A. In-memory JS arrays | 0 KB | ~100K rows | Crashes on AR; definitely on IN |
| **B. DuckDB-WASM over Parquet (HTTP range)** | ~6 MB async | billions of rows | SQL over parquet without parsing whole file; precise SQL → fast results; bundle loaded async after first paint |
| C. hyparquet + JS-side filtering | 30 KB | ~1M rows | No SQL; slow for joins; we'd reinvent half of DuckDB |
| D. Arrow + AlaSQL | 1 MB | ~500K rows | Weaker than DuckDB; halfway solution |
| E. Server-side query API | — | infinite | We have no server |

**Locked: B (DuckDB-WASM).** The 6 MB bundle amortizes across every
filter, sort, search, and detail-panel fetch. Loaded async so doesn't
block first paint. Returns matching `parcel_id`s, which we push to
MapLibre via `setFeatureState` to fade non-matches.

### Decision 6 — Catalog / discovery

| Option | Per-load cost | Verdict |
|---|---|---|
| A. Probe 50 FIPS for catalog.json (current) | 50 HTTP requests | Wasted bandwidth at scale |
| B. Single global manifest.json | 1 HTTP request | Needs regeneration after each compose |
| **C. Both (hybrid)** | 1 + per-state-as-needed | Tiny manifest at composite root drives state list; per-state catalog loaded only when state selected |

**Locked: C.** Add `data/processed/composite/manifest.json` (<10 KB even
at 50 states). Per-state `catalog.json` unchanged.

### Decision 7 — Filter-facet population

| Option | Verdict |
|---|---|
| A. Live DuckDB `SELECT DISTINCT … GROUP BY` on every filter open | Slow first paint of filter controls |
| **B. Precompute facets.json at preprocess time** | <100 KB / state; instant initial render |
| **C. Both — facets for initial render; DuckDB for dependent-filter recounting** | The right answer |

**Locked: C (precompute + live for dependent counts).**

### Decision 8 — County choropleth source

`county_scores.parquet` has only `county_fips + tier`, no geometry. We
need polygons.

| Option | Verdict |
|---|---|
| A. Bundle TIGER counties as static national asset (~30 MB simplified) | Wasteful per-state; loads counties we don't need |
| B. Dissolve from parcels | Slow + ugly boundaries |
| **C. Clip TIGER counties per state at preprocess time, write `county_boundaries.geojson` (~50 KB / state)** | Clean, small, ships in catalog |
| D. External tile server | Adds infra |

**Locked: C.** Adds a new data source to the puller (TIGER counties) + a
preprocess step. ~1 day of work in Phase 5.

### Decision 9 — Build / deploy artifact

| Option | Verdict |
|---|---|
| A. Commit `app/dist/` so users without Node can serve | Standard practice for static sites |
| B. Force users to `npm install && npm build` | Friction for non-frontend devs |
| **C. Commit `dist/` AND keep `npm run dev` for active dev** | Best of both |

**Locked: C.** Node required only for active frontend work.

### Decision 10 — Test stack

| Test type | Tool | Why |
|---|---|---|
| Unit (store mutations, formatters, SQL composer) | **Vitest** | Vite-native; <100ms test runs |
| Integration (DuckDB query semantics on fixture parquet) | Vitest + tiny fixture parquet | Schema-locks the contract |
| E2E (user flows in a real browser) | **Playwright** | Best-in-class; cross-browser; supports map/canvas inspection |
| Visual regression (sidebar layout, detail panel) | Playwright screenshots + baseline | Cheap insurance |
| Performance budgets | Playwright + `performance.now()` assertions | Numerical CI gate |
| Data contract (catalog.json, facets.json conform) | JSON Schema validation in preprocess | Fails build if preprocess and frontend drift |

### Decision 11 — Folder structure

- `app/` → **deprecated**, kept as fallback until app2 ships, then deleted
- `app2/` → new Svelte/Vite project, becomes `app/` at end of Phase 9
- `data/processed/composite/manifest.json` → **new** global state list
- `data/processed/composite/<fips>/parcels.pmtiles` → **new**
- `data/processed/composite/<fips>/county_boundaries.geojson` → **new**
- `data/processed/composite/<fips>/facets.json` → **new**
- `scripts/preprocess/tiles.py` → **new**
- `scripts/preprocess/facets.py` → **new**
- `scripts/preprocess/county_boundaries.py` → **new**

### Decision 12 — What I do if a phase reveals the design is wrong

Stop, communicate the issue, propose a revised plan. **No silent
pivots.** Every phase ends in a green test suite or it doesn't end.

---

## Part 2 — Phased plan

Each phase: **2–4 days of focused work**, has explicit acceptance
criteria + automated tests, ships independently usable progress.

### Phase 0 — Spike & scaffolding (1–2 days)

**Goal:** prove the stack works end-to-end on the smallest possible slice.

**Deliverables**
- `app2/` Svelte+Vite+TS project scaffolded
- Dependencies installed: `maplibre-gl`, `pmtiles`, `@duckdb/duckdb-wasm`,
  `svelte`, `vite`, `vitest`, `@playwright/test`
- App boots, MapLibre renders OSM basemap centered on FL bbox
- Hard-coded test: loads `data/processed/composite/12/towers.geojson`,
  drops markers
- README in `app2/` describes setup

**Tests (all green to exit phase)**
- Playwright spec: page loads, basemap tiles appear, no console errors
- Vitest spec: smoke test on one trivial pure function (proves test runner works)

**Risk:** None significant. Throwaway code if needed.

---

### Phase 1 — PMTiles generation pipeline (3–4 days)

**Goal:** every state's parcels are queryable as vector tiles in the
browser. Confirmed on IN (3.7M rows).

**Deliverables**
- `scripts/preprocess/tiles.py` — streams parcels.parquet → NDJSON via
  `pyarrow.dataset` → pipes into `tippecanoe -o parcels.pmtiles -l parcels
  -z 14 -Z 6 --drop-densest-as-needed --no-tile-compression`
- Subprocess with backpressure handling + clean error propagation
  (tippecanoe failure → Python raises)
- Tile attributes carry only: `parcel_id`, `owner_kind`, `distress_tier`,
  `has_tower`, `has_solar`, `has_billboard`, `in_oz`, `interestingness_score`
  (the styling/filtering minimal set)
- New `--skip-tiles` CLI flag for users without tippecanoe
- Tippecanoe missing → preprocess prints actionable error and continues without tiles
- catalog.json gains `layers.parcels.pmtiles_path` when present
- Generate tiles for AR, FL, IN
- Frontend (in app2): parcels now render from PMTiles via MapLibre, not GeoJSON
- Zoom 6 → simplified blocks of parcels per county; zoom 14 → individual
  parcel polygons; smooth transitions

**Tests**
- `pmtiles show data/processed/composite/05/parcels.pmtiles` succeeds,
  reports correct feature count
- Unit: `scripts/preprocess/tiles.py` invoked on a 10-row fixture
  produces a valid pmtiles file
- E2E: Playwright opens app pointed at IN, pans + zooms 5 times,
  asserts (a) no console errors, (b) tiles requests succeed
- **Performance budget:** time-to-first-parcel-paint on IN ≤ 1.0s on local server

**Risk:** Tippecanoe parameter tuning (zoom range, simplification) may
need iteration to balance file size vs visual quality. Mitigation: start
with conservative defaults from Mapbox's playbook, profile after.

**Blocker:** OK to add `tippecanoe` as a Homebrew dependency? (~30 sec install)

---

### Phase 2 — UI shell rewrite in Svelte (2–3 days)

**Goal:** every piece of UI chrome in the current app is reimplemented
in Svelte, driven by catalog.json. No hardcoded "Graham County, NC" anywhere.

**Deliverables**
- `manifest.json` writer added to preprocess (composes a list of all completed states)
- Svelte stores: `activeState`, `catalog`, `layers`, `filters`, `selection`
- Components: `<Sidebar>`, `<StateSelector>` (from manifest),
  `<LayerToggle>` (per catalog.layers), `<ViewToggle>` (per catalog.views),
  `<SummaryCard>`, `<DetailsPanel>`
- Title bar, subtitle, footer all driven by `catalog.state_name`
- URL state: `?state=05` selects state; reflects in dropdown
- Layer registry: declarative — each canonical_type in `catalog.layers`
  maps to a known renderer; unknown types log a warning, don't crash

**Tests**
- Vitest: store mutations behave correctly (set filters → derived
  `activeFilterCount` updates)
- E2E: state dropdown lists FL/AR/IN; selecting one navigates +
  re-renders; title bar updates
- Visual regression: baseline screenshots of sidebar at default state per state

**Risk:** Low. Mostly straightforward porting.

---

### Phase 3 — DuckDB-WASM filter engine (3–4 days)

**Goal:** every v3 schema field is filterable; filter response < 500ms
on IN (3.7M rows).

**Deliverables**
- DuckDB-WASM initialized once per state load; HTTPS range-request
  handle on `parcels.parquet`
- Filter abstraction: each filter component owns
  `{column, operator, value}`; a `composeQuery()` function assembles
  WHERE clauses
- Result pipeline: query returns matching parcel_ids → batched into
  MapLibre `setFeatureState` calls → MapLibre paint expression fades
  non-matches
- `facets.json` precomputed by new `scripts/preprocess/facets.py`
  (distinct values + counts for categoricals, min/max for numerics)
- Filter UI:
  - `owner_kind` multi-select (chips with counts from facets)
  - `distress_tier` multi-select
  - `has_tower` / `has_solar` / `has_billboard` checkboxes
  - `in_oz` / `in_qct` / `persistent_poverty` checkboxes
  - `interestingness_score >= X` slider (0–1)
  - `owner_cluster_size >= N` slider
  - `assessed_value` range slider
  - `acreage` range slider
  - `county_fips` multi-select (driven by county_boundaries)
- "Reset all filters" button
- Live filter-count badge ("12,345 parcels match")

**Tests**
- Unit: SQL composer (8 filter-combo fixtures → expected WHERE clauses, byte-for-byte)
- Integration: each filter combination against fixture parquet → expected row counts
- E2E: apply 3 filters → map fades non-matches → filter-count badge
  updates → reset button restores
- **Performance budget:** 3-filter compound query on IN parcels < 500ms
  median, < 1000ms p95

**Risk:** DuckDB-WASM cold-start latency. Mitigation: load the WASM
binary async during initial paint, show a "filters loading…" skeleton.

---

### Phase 4 — Detail panels (2 days)

**Goal:** clicking any feature shows everything v3 knows about it.

**Deliverables**
- Click parcel in MapLibre → emits parcel_id → DuckDB fetches the single
  row → Svelte renders panel
- Parcel panel shows: owner, owner_kind, mailing addr, situs addr,
  acreage, assessments, land use, county, all distress flags, infra
  summary (towers + solar + billboards on parcel), interestingness score
  with components broken out, owner cluster info (size, total value,
  "see all parcels" button)
- "See all parcels by this owner" button → applies `owner_cluster_id = X` filter
- Tower panel: FCC ASR fields + nearby solar + landowner cluster context
- Solar / billboard panels (when those layers active)
- Sticky panel position; close button

**Tests**
- E2E: click a parcel known to host a tower → panel renders within 200ms
  with expected owner name
- E2E: "see all parcels by this owner" → map updates, sidebar shows N
  matching parcels
- Visual: detail panel snapshot for parcel + tower + solar

**Risk:** Low.

---

### Phase 5 — Auxiliary layers (2 days)

**Goal:** every canonical type in the catalog has a first-class layer.

**Deliverables**
- Solar facilities: GeoJSON → orange diamond markers + native MapLibre clustering at low zoom
- Billboards: distinct icon, also clustered
- Distress overlays: replaces OZ-only treatment; styled by `distress_tier`
  with multi-tier palette
- County choropleth:
  - **New data source:** TIGER county shapefile (national, ~80 MB; goes
    in puller as `tiger_counties` source, MANUAL_ONLY since user must
    download from census.gov)
  - **New `scripts/preprocess/county_boundaries.py`** clips TIGER
    counties to state bbox + left-joins `county_scores` (gets `tier`,
    `persistent_poverty`)
  - Writes `county_boundaries.geojson` per state
  - Frontend renders as translucent choropleth; toggleable
- Legend regenerates from active layers

**Tests**
- Unit: clip function returns 75 counties for AR, 67 for FL, 92 for IN
- E2E: toggle each layer on → it appears → click a feature → detail panel
- Visual: county choropleth screenshot per state

**Risk:** Medium — TIGER counties are a new data source you have to download.

---

### Phase 6 — Top-N panel + owner/APN search (2 days)

**Goal:** the highest-value parcels in any state surfaceable in <1 click.

**Deliverables**
- Top-N panel reads `views/interestingness_top_1000.parquet` via DuckDB
- Virtualized list (only render visible rows; constant memory regardless
  of total rows)
- Sortable columns: score, owner, county, value
- Click row → map flies to parcel + opens detail panel
- Owner search:
  - Live DuckDB ILIKE on `owner_name_norm`
  - Debounced 200ms
  - Top 10 suggestions in dropdown
  - Click → applies `owner_cluster_id` filter
- APN exact-match search:
  - `parcel_id = ?` query
  - On hit → fly to + select

**Tests**
- Unit: virtual list renders 1000 rows with consistent DOM node count
  regardless of scroll position
- E2E: type "smith" → suggestions appear → click → map updates
- E2E: type known APN → parcel highlighted + centered
- **Performance budget:** search keystroke → suggestion < 200ms

**Risk:** Low.

---

### Phase 7 — URL state + polish (1–2 days)

**Goal:** any view is shareable as a URL.

**Deliverables**
- URL state: `?state=05&filters=<encoded>&selected=<parcel_id>` reflects
  + restores all UI state
- Loading skeletons for slow first-tile, slow DuckDB warmup
- Error boundaries: catalog load failure / tile load failure render
  actionable messages
- Keyboard shortcuts: `f` focuses filter; `Esc` clears selection; `?` shows
  shortcut overlay
- "Copy link" button in header

**Tests**
- E2E: load app with `?state=12&filters=owner_kind:LLC` → boots into
  filtered LLC view
- E2E: select parcel → URL updates → reload page → same parcel re-selected
- Lighthouse score > 90 on FL load

**Risk:** Low.

---

### Phase 8 — Performance hardening + cross-state view (2 days)

**Goal:** every performance budget defined in earlier phases is green;
bonus cross-state comparison.

**Deliverables**
- Profile-driven tuning: bundle splitting (DuckDB lazy), tile cache
  headers, code splitting per route
- Service worker caches basemap + manifest + catalog
- Cross-state summary page: `/compare?states=05,12,18` shows small
  multiples (counts, top-1000 LLC owners per state side-by-side)
- Compose a `compare.json` precomputed cross-state aggregate at preprocess time

**Tests**
- All performance budgets green
- E2E: compare page renders for 3 states in < 3s

**Risk:** Low. Stretch goal.

---

### Phase 9 — Cutover + docs (1 day)

**Goal:** `app2/` becomes `app/`; old app deleted; docs updated.

**Deliverables**
- `git mv app app_legacy_v1 && git mv app2 app`
- README rewritten
- CLAUDE.md updated
- New `app/ARCHITECTURE.md` documenting tech stack + tile pipeline +
  filter engine
- `dist/` built & committed
- Smoke test in CI / pre-commit hook validates dist still serves

**Tests**
- Final Playwright suite passes against the served `dist/`
- Manual checklist of every feature (one-page user-acceptance doc)

**Risk:** Low.

---

## Part 3 — Total timeline

| Phase | Days | Cumulative |
|---|---|---|
| 0. Spike | 1–2 | 1–2 |
| 1. PMTiles | 3–4 | 4–6 |
| 2. UI shell | 2–3 | 6–9 |
| 3. Filter engine | 3–4 | 9–13 |
| 4. Detail panels | 2 | 11–15 |
| 5. Aux layers | 2 | 13–17 |
| 6. Top-N + search | 2 | 15–19 |
| 7. URL state + polish | 1–2 | 16–21 |
| 8. Perf + cross-state | 2 | 18–23 |
| 9. Cutover | 1 | 19–24 |

**Range: 19–24 working days (~4–5 weeks of focused dev).**

Work plan: **2-phase batches** for the early phases (0–1, 2–3, 4–5) since
architectural choices solidify, then full speed through 6–9. Or all at
once if you want to come back to a finished thing — your call.

---

## Part 4 — Blockers / questions for the user

These will materially affect the plan:

1. **Tippecanoe install OK?** `brew install tippecanoe` (~30 sec).
   Required for Phase 1. Without it I'd have to invent a much worse tile
   generator. *Strong recommend yes.*

2. **Node.js + npm install OK?** Required for Svelte/Vite/Playwright.
   ~100 MB on disk. Required for Phase 0 onward. *Required.*

3. **TIGER counties as a new data source?** Adds one MANUAL_ONLY
   download (~80 MB national, you download from census.gov once).
   Required for Phase 5. *Recommend yes.*

4. **PMTiles file sizes:** IN parcels will produce ~200–500 MB pmtiles.
   Acceptable on disk. If we ever host on GitHub Pages, files >100 MB
   need Git LFS. **Where will this eventually be deployed?**

5. **Mobile support — Phase 1 or defer to a future Phase 10?** Current
   plan is desktop-first. *Recommend defer.*

6. **Build alongside (`app2/`) or in-place feature branch?** Plan
   assumes `app2/` so current app keeps working through the rebuild.
   Alternative is a long-lived `feat/app-v2` branch. *Recommend `app2/`
   directory.*

7. **TypeScript: hand-maintained types or codegen from Python schemas?**
   I propose hand-maintained types in `app2/src/lib/schema.ts` for Phase
   0, with the option to add codegen in a later phase if drift becomes a
   problem. *Recommend hand-maintained for now.*

8. **What's the "exceptional" success metric?** I'd like to make sure
   I'm aiming at the right target. Candidates:
   - **Reliability:** zero data loss; every panel always populates correctly;
     tests catch regressions automatically.
   - **Speed:** all interactions < 500ms; smooth panning on 3.7M parcels.
   - **Insight:** the top-N + filters consistently surface the
     actually-interesting opportunities a user wouldn't find otherwise.
   - **All three.** *I'll assume this unless you say otherwise.*

9. **Single-user or eventual team?** Affects whether I invest in things
   like documented store contracts, JSDoc on every export, etc. *I'll
   default to "single user but well-documented" so future collaborators
   can ramp.*

---

## Part 5 — What I'll do without further input

Once you sign off (and answer 1–4 explicitly), I'll start with **Phase 0
+ Phase 1 as a single batch** and report back when:

- The spike is green
- IN parcels render at 60 fps from PMTiles in the browser
- The full Phase 1 test suite is green

After that, I'll proceed in 2-phase batches with progress reports
between each.

If any of the locked-in decisions (Part 1) feel wrong, push back now —
those are expensive to revisit later.
