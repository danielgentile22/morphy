# Performance Audit — 2026-06-07

> **REPORT-ONLY.** This pass changed **zero application code**. The sole deliverable is this document. Every fix below is a *proposed* work order to be applied (and reviewed) in a separate, later pass — see [Hand-off](#6-hand-off--how-to-apply-these). All live validation ran **locally only**; production (`morphyconsulting.com` and the prod DB) was never contacted.

**Scope:** codebase-wide inspect-first sweep across all five subsystems (map app, FastAPI backend, preprocess ETL, headless + desktop pullers), covering both **compute efficiency** and **perceived/delivery** performance. Produced per [PRD #123](https://github.com/danielgentile22/infra-lease-analytics/issues/123).

**Method:** a multi-agent sweep — 6 parallel finders (one per PRD lane) → dedup + rank by impact × certainty with the PRD weighting → **local live-validation of the top findings** (real `vite` split build, `EXPLAIN QUERY PLAN`, a Chrome network/Lighthouse pass on `vite preview`, a timed preprocess benchmark) → this synthesis. **50 raw findings → 42 ranked** (8 same-root-cause merges).

**Counts:** 34 main-report findings (high/medium confidence) + 8 speculative (low confidence, [Appendix A](#appendix-a--speculative-low-confidence)). 14 of the main findings are quick-wins.

---

## 1. Executive summary

Nothing in the app is *broken*, but the audit found one **structurally oversized cold-start** and a cluster of **un-throttled, full-collection recompute storms** on the exact surfaces the co-founder touches every day. The single biggest lever is that **the Dashboard landing eagerly downloads and parses the entire Explore map stack** — measured live — even though the Dashboard needs none of it. The backend read path has a handful of clean, high-certainty wins (a measured index filesort, redundant full-index scans, a double activity scan). The ETL and pullers carry real but lower-weight batch wins.

### 1.1 Headline wins (top 5)

| # | Finding | Expected gain | Certainty | Effort |
|---|---|---|---|---|
| 1 | **PERF-001** Defer the entire Explore map stack (DuckDB WASM + tower/sola | (estimate) multi-second cold-load improvement: landing no longer blocked on ~7MB gzip WASM + ~6MB parquet + ~750KB gzip solar +… | measured | 🔧 small |
| 2 | **PERF-002** Re-introduce the lost debounce on the filter sliders: each o | ~20x reduction in this cascade's work per drag; eliminates per-tick main-thread long tasks during slider interaction. | high | 🔧 small |
| 3 | **PERF-003** Same un-debounced storm on the scoring-weight sliders: each  | ~20x fewer scoreById rebuilds and Explore/Leads re-sorts per weight drag; removes per-tick long tasks while tuning weights. | high | 🔧 small |
| 4 | **PERF-004** Code-split the 1.4MB single JS chunk | (estimate) Repeat-visit JS download drops from ~379KB gzip to the app-only delta (tens of KB) whenever only app code changes; v… | measured | ⚡ quick-win |
| 5 | **PERF-005** Derive /api/counts from the persisted-lead set (and share na | counts becomes O(persisted_leads) (e.g | measured | ⚡ quick-win |

1. **PERF-001 — Defer the Explore map stack off the Dashboard landing.** *Measured:* on landing the browser pulls `owners_filter.json` **10.6 MB** + solar **2.77 MB** + four `towers.parquet` + DuckDB worker **755 KB** + MapLibre worker **447 KB** — none needed to render the Dashboard. Deferring these to first-Explore removes a multi-second, multi-megabyte cold start from every session's landing.
2. **PERF-002 / PERF-003 — Re-introduce the lost slider debounce.** Each `oninput` tick on a filter/scoring slider runs a full 16,237-owner predicate scan + 80,814-feature dedup/sort/re-cluster, **un-debounced** (~20 ticks per drag). A ~150 ms debounce collapses ~20× of main-thread work on the primary triage control.
3. **PERF-004 — Code-split the 1.4 MB single JS chunk.** *Measured:* `manualChunks` drops the app chunk **388 KB → 51 KB gzip (−87%)** and isolates MapLibre/DuckDB as cacheable vendor chunks that daily app-code deploys no longer invalidate.
4. **PERF-005 / PERF-009 — Stop the backend re-scanning the whole 16,237-owner index per read.** *Measured:* `counts()` does up to 3 full 16k passes per nav; an override-tenant single-owner read rebuilds the whole index (**~10.8 ms/call**). Deriving counts from the tiny persisted-lead set + memoizing `effective()` make these O(persisted) / O(1).
5. **PERF-006 — Composite index on `contact_attempt`.** *Measured:* `EXPLAIN` confirms a `TEMP B-TREE` filesort on every Lead-page / activity / stats read; the composite index makes it vanish.

### 1.2 Total estimated gain (grouped)

- **Cold-load / first paint** (PERF-001, 004, 011, 012, 013, 014, 018, 036): the Dashboard landing goes from downloading+parsing **~20 MB of map assets** (10.6 MB owners filter + ~6 MB towers parquet + 2.77 MB solar + ~1.2 MB workers) and a **1.4 MB / 388 KB-gz** JS chunk, down to a **51 KB-gz** app chunk plus the two small Dashboard API calls. Headline, measured, user-facing.
- **Interaction responsiveness** (PERF-002, 003, 007, 010): ~**20× fewer** full-collection recompute cascades per slider drag on the map/filter/scoring surfaces (each cascade = a 16,237-owner scan + an 80,814-point re-cluster).
- **Backend read path** (PERF-005, 006, 008, 009, 017, 022, 024): counts O(16k)→O(persisted) (~80× fewer iterations at a 200-lead tenant), the `contact_attempt` filesort removed (measured), `/api/activity` 2×→1× scan, `effective()` memoized (~200× fewer rebuilds on an activity feed), ~2,000 fewer Pydantic validations per worklist call.
- **ETL throughput** (PERF-015, 016, 020, 021, 028, 029): real per-pass and per-row wins on the dev-side batch — but **measurement tempered PERF-015**: interestingness scoring is only ~3% of compose wall-clock, so PERF-016 (eliminate one full parcel-geometry sweep per state, ~−33% of the infra pre-pass) is the larger ETL lever.
- **Memory** (PERF-026): the 41 MB owners index parses to an estimated ~150–250 MB RSS per worker — bounding it is what lets worker count scale on the constrained Fly host.

### 1.3 Quick-win shortlist

High-value, low-effort, low-risk — batch these first:

| Finding | One-line | Gain |
|---|---|---|
| **PERF-004** ✅ | Code-split the 1.4MB single JS chunk | (estimate) Repeat-visit JS download drops from ~379KB gzip to the app-only delta (tens … |
| **PERF-005** ✅ | Derive /api/counts from the persisted-lead set (and share nav passes)  | counts becomes O(persisted_leads) (e.g |
| **PERF-006** ✅ | Add composite indexes on contact_attempt to kill the TEMP B-TREE files | Eliminates the temp B-tree sort on all three queries; list_attempts gets a direct index… |
| **PERF-007** | StatStrip 'Towers' count materializes the full deduped+sorted 80,814-r | Removes the O(n log n) sort + ~80K object allocations from every count update; count be… |
| **PERF-014** ✅ | Solar GeoJSON (~2.7MB, FL=2.2MB) downloaded + parsed at boot although  | Removes ~2.7MB download + parse from boot for the common case (~0.7MB gzip wire + parse… |
| **PERF-018** ✅ | favicon.png is 98.8KB | ~96KB saved per uncached load; trivial but free. |
| **PERF-019** | Production serving: add immutable cache headers on hashed /assets/* an | (estimate) Repeat-visit asset transfer → ~0 (304s eliminated) for hashed assets; first-… |
| **PERF-020** ✅ | Vectorize geom_bbox construction (row-wise apply over all parcels at n | `bounds[['minx','miny','maxx','maxy']].to_numpy().tolist()` is ~50-100x faster for this… |
| **PERF-021** | Hoist county_score rollup out of the per-shard loop (prepare() recompu | N_shards → 1 county_score rollups per state (~67x → 1x for FL) |
| **PERF-022** | Collapse lead_view's per-merged-member attempt queries into one IN-que | 1 query instead of len(members) for the Lead page; removes the Python re-sort if the si… |
| **PERF-024** | Eliminate the redundant in-route Pydantic validation pass on the list  | Halves per-row Pydantic work (one validation pass instead of two) — up to ~2000 fewer m… |
| **PERF-031** | Stop the 5-second QTimer from re-walking the entire 55 GB raw tree on  | Eliminates ~18,000 stat/min of UI-thread I/O; header refresh drops from O(1,498 files) … |
| **PERF-032** | Use cached manifest bytes in _refresh_row instead of re-statting each  | Per-row disk walk → O(1) manifest read |
| **PERF-034** | ScoringPreset default-toggle re-queries all presets instead of one UPD | Replaces SELECT-all + per-row ORM mutation with one targeted UPDATE on set-default/crea… |

✅ = number live-measured locally (see [§3](#3-local-validation-results-phase-3)).

---

## 2. Method, weighting & rails

**Lanes & weights (PRD-locked, "who waits"):** Frontend compute = HIGH · Frontend perceived/delivery = HIGH · Backend reads = HIGH · Backend compute/auth = MED-HIGH · Preprocess ETL = MED · Pullers = LOW. Within a lane, user-facing triage surfaces (map cold-load, tower clicks, filtering, the Lead page) are weighted highest — a fix the co-founder feels during daily triage outranks an equal-magnitude batch win.

**Ranking:** impact × certainty under that weighting. High/medium certainty → main report; low certainty → [Appendix A](#appendix-a--speculative-low-confidence). A numeric gain in the main report is either live-measured (§3) or explicitly tagged `(estimate)`.

**Rails respected (no recommendation violates a locked decision):** tenant-scoped backend (ADR-055); owners-index schema-versioning with safe defaults; single-place merge/split coalesce in `OwnersIndexService.effective` (ADR-056); chunked-compose memory posture (ADR-051) is *characterized, not redesigned*; the unauthenticated `:8765` static map-data server is accepted posture, **not** a finding; per-request `users.txt` re-authorization (ADR-062/063) is cost-characterized, **not** removed; EPSG:4326 / no-normalize-filtering / no-Qt-in-`scripts/fetch` preserved. New dependencies are flagged inside the finding, never assumed (only `orjson` and a brotli Caddy plugin are mentioned, both flagged + optional).

---

## 3. Local validation results (Phase 3)

All run locally; production untouched; the git tree was clean before and after (verified). Temp artifacts (split build, DB copy, throwaway vite config) were removed.

| Finding | Method | Result |
|---|---|---|
| **PERF-004** | real `vite` `manualChunks` build → temp dir | app `index` chunk **1,464 KB → 179 KB raw** (−88%), **388 KB → 51 KB gzip** (−87%); maplibre 273 KB gz + duckdb 45 KB gz carved out; +69.8 KB MapLibre CSS chunk |
| **PERF-001 / 013 / 014 / 018** | Chrome network capture on `vite preview` Dashboard landing (dev/dev) | on landing: owners_filter **10,637 KB**, solar **~2.77 MB**, 4× towers.parquet, DuckDB worker **755 KB**, MapLibre worker **447 KB**, index.js 1,430 KB/379 KB gz, favicon **97 KB** — all before Explore opened; owners_filter served **uncompressed** locally |
| **PERF-006** | `EXPLAIN QUERY PLAN`, before/after on a temp DB copy | before: both attempt queries `USE TEMP B-TREE FOR ORDER BY`; after composite indexes: filesort **gone**, direct index range scans |
| **PERF-008** | code path read | `tenant_attempts()` called **twice** per `/api/activity` (events :70 + digest :104) |
| **PERF-009** | `timeit` over real 16,237-owner index | `effective()` regroup+index = **~10.8 ms/call**, paid per single-owner read under overrides |
| **PERF-005** | `timeit` over real index | full counts pass **~2.3 ms warm** (floor; ≤3 passes/nav; prod slower) |
| **PERF-015** | surgical benchmark on real MT parcels | interestingness scoring **~62,877 rows/sec** = only **~3% of MT compose wall-clock** → impact **tempered** (see finding) |
| **PERF-020** | code path read | `geom.py:94` confirmed row-wise `apply(axis=1)` over every parcel |

> **Not validated (left as labeled estimates):** the *after* numbers for interaction findings (PERF-002/003/007/010) require implementing the fix, which this report-only pass does not do — their *before* cost (un-debounced full-collection cascades) is confirmed structurally. A full Lighthouse score and a timed full-county recompose were skipped in favor of the cheaper, equally-conclusive network/EXPLAIN/benchmark measurements above.

---

## 4. Ranked findings (main report)

Each finding is a self-contained work order. **Execution** is written to be pasted straight back to Claude as implementation instructions. Certainty badges: 🟢 high · 🟡 medium · ⚪ low. Effort: ⚡ quick-win · 🔧 small · 🏗️ larger refactor. ✅ = a number was live-measured locally.

### PERF-001 — Defer the entire Explore map stack (DuckDB WASM + tower/solar/owner data + MapLibre mount) off the Dashboard-landing critical path

**Rank 1**  ·  app/ frontend — perceived/delivery (boot path)  ·  _perceived_  ·  certainty 🟢 high  ·  effort 🔧 small  ·  ✅ CONFIRMED (measured · local)

- **Location:** app/src/App.svelte:76-81 (boot $effect), :309-310 (always-mounted <MapView/>); app/src/lib/stores.svelte.ts:116-150 (boot loads towers+solar+parcel probes); app/src/components/MapView.svelte:131 (onMount new maplibregl.Map); app/src/components/FilterPanel.svelte:18 (onMount filterModel.load); app/src/lib/nav.ts:48
- **What & why:** The app opens on the Dashboard, but .explore-layout (MapView + always-mounted FilterPanel sidebar) renders the instant auth.verified is true, and app.boot() fires regardless of route. On the landing page the user implicitly waits behind: MapLibre new Map() + basemap tiles; duckDb.init() pulling the DuckDB eh WASM because loadTowers() runs immediately; ~6MB per-state towers.parquet over HTTP range; ~2.7MB solar GeoJSON; and the 10.89MB owners_filter.json via FilterPanel onMount. None of this is needed to render the Dashboard, which only needs /api/counts + /api/attention. Single largest perceived-latency lever.
- **Grounded impact (real N):** Removes from landing TTI: DuckDB eh WASM (34MB raw / ~7MB gzip — largest single cold-start payload), ~6MB tower parquet (80,814 towers), ~2.7MB solar GeoJSON, the 10.89MB owners_filter.json (722KB gzip but a 10.6MB main-thread parse of 16,237 owners), plus 80,814 SHA-1 hashes. Fixed costs paid on every cold load on shared-cpu-1x.
- **Expected gain:** (estimate) multi-second cold-load improvement: landing no longer blocked on ~7MB gzip WASM + ~6MB parquet + ~750KB gzip solar + 722KB gzip owners JSON and their parse/CPU.
- **✅ Local validation — CONFIRMED (measured · local):** Network waterfall on the **Dashboard landing** (`vite preview` :4173, dev/dev login) shows the full Explore map stack firing before Explore was ever opened: `owners_filter.json` **10,637 KB**, solar GeoJSON **~2.77 MB** (FL 2,228 + AR 354 + MT 97 + WV 86 KB), all four `towers.parquet`, **DuckDB eh.worker 755 KB** (decoded) + **MapLibre worker 447 KB** (decoded), main `index.js` 1,430 KB decoded / 379 KB gz. The Dashboard demonstrably pays for the entire map stack.
- **Execution (paste-back work order):** Latch the first reveal: `let mapEverShown=$state(false); $effect(()=>{ if(section==='explore'||route.name==='tower'||route.name==='lead') mapEverShown=true; });` then wrap <MapView/> (App.svelte:310) and the FilterPanel sidebar in {#if mapEverShown}. Split app.boot(): keep index fetch + counts/attention unconditional; gate loadTowers()/loadSolar()/parcel probes (stores.svelte.ts:129-136) behind a new app.bootMap() called once when the map is first shown. Once mounted, never unmount (ADR-061). LeadPage already calls filterModel.load() itself (LeadPage.svelte:28), so dropping FilterPanel-onMount eager load is safe for the lead path.
- **Behavior risk & rollback:** First Explore visit pays the WASM/parquet cost it used to pay at boot (one-time, with the existing loading pill). A deep link to #/explore must trigger the latch immediately (route check covers it). Rollback: revert the latch so MapView + bootMap mount unconditionally.
- **Suggested confirm-it measurement:** chrome-devtools lighthouse + list_network_requests on localhost:5173 landing on Dashboard, before/after; confirm duckdb-eh.wasm + *.parquet + owners_filter.json no longer fire until Explore opens.
- **⚠️ Rail / dependency flag:** ADR-061 map persistence — satisfied by lazy FIRST mount then never unmounting. No new dependency.
- **Merged from:** none (fe-perceived). Subsumes part of PERF-011/013/014 on the landing path; those remain as deeper per-asset fixes for first-Explore.
- **Why this rank:** Biggest cold-load lever × high certainty × co-founder lands here every session — top of the who-waits weighting.

---

### PERF-002 — Re-introduce the lost debounce on the filter sliders: each oninput tick triggers a full 16,237-owner + 80,814-feature recompute cascade

**Rank 2**  ·  fe-compute / shared FilterModel projection  ·  _compute_  ·  certainty 🟢 high  ·  effort 🔧 small

- **Location:** app/src/components/FilterPanel.svelte:38-48,209-210,241-242,271-272,284-285 (sliders fire oninput→updateFilter); app/src/lib/filter-model.svelte.ts:49-56,125-127 (matchingClusterIds $derived.by + updateFilter); app/src/lib/explore-towers.svelte.ts:19-26; app/src/components/MapView.svelte:582-589,481-500
- **What & why:** The numeric filter sliders + assessed-value inputs call updateFilter on EVERY oninput tick with no debounce. Each reassignment synchronously re-runs on the main thread: (1) matchingClusterIds — full scan of 16,237 owners (up to 14 active-field predicates each) building a fresh Set; (2) exploreTowers.rows — full scan of all 80,814 tower features into a dedup Map + sort; (3) MapView's tower $effect → filterTowers → src.setData (full feature scan + re-ingest). The old parcel path had a 160ms debounce (FILTER_DEBOUNCE_MS in filter-engine.ts) but that engine was orphaned in the redesign, so the live path runs fully un-debounced. A score-slider drag (step 0.05, 0→1) is ~20 ticks, each paying the full cascade.
- **Grounded impact (real N):** ~20 ticks/drag × (16,237-owner predicate scan + 80,814-feature dedup/sort + a full GeoJSON rebuild + setData re-ingest) ≈ ~4.5M owner-field evals + ~3.2M feature visits + 20 full GeoJSON rebuilds per single slider drag. This is the co-founder's primary daily triage control.
- **Expected gain:** ~20x reduction in this cascade's work per drag; eliminates per-tick main-thread long tasks during slider interaction.
- **Execution (paste-back work order):** In FilterPanel.svelte decouple the slider's visual value from the committed model: bind each range input to a local $state value (thumb stays responsive) and debounce the commit to filterModel.updateFilter(...). Add a shared debounce helper (one setTimeout ref, ~120-160ms — reuse the dead FILTER_DEBOUNCE_MS constant) routing setNum/setAssessed through it. Keep multi-select toggles/checkboxes immediate (one event per click). Optionally precompute per-field inverted owner-id buckets so matchingClusterIds intersects active dimensions instead of full-scanning. Verify matchingClusterIds, exploreTowers.rows, and the MapView tower $effect each run once per settled value.
- **Behavior risk & rollback:** Blast radius: FilterPanel slider UX. The Towers count tile + map fade update on a short delay instead of per pixel — acceptable. Rollback: revert FilterPanel to call updateFilter directly. No data/schema/tenant changes.
- **Suggested confirm-it measurement:** chrome-devtools performance_start_trace, drag the score slider on localhost:5173, performance_stop_trace; compare scripting time / long-task count. Alt: console.time inside matchingClusterIds and count invocations per drag.
- **Merged from:** fe-compute #1 + fe-perceived #15 (matchingClusterIds full owner scan; same un-debounced filter recompute root cause, primary fix is debounce).
- **Why this rank:** High certainty × ~20x × the single most-used triage control — felt on every filter drag.

---

### PERF-003 — Same un-debounced storm on the scoring-weight sliders: each tick rebuilds the 16,237-entry score Map and re-sorts 80,814 Explore rows + Leads

**Rank 3**  ·  fe-compute / tunable scoring  ·  _compute_  ·  certainty 🟢 high  ·  effort 🔧 small

- **Location:** app/src/components/ScoringPanel.svelte:90-98 (weight slider oninput→setWeight); app/src/lib/scoring-store.svelte.ts:53-79 (scoreById $derived.by + setWeight); app/src/lib/explore-towers.svelte.ts:19-26; app/src/components/Leads.svelte:19-26; app/src/components/MyLeads.svelte:21-33
- **What & why:** Each weight range input fires setWeight per oninput tick, reassigning config and flipping into custom mode, invalidating scoreById ($derived.by) which rebuilds a Map over all owners calling effectiveScore→scoreOwner (a 9-weight blend) each. Because exploreTowers.rows, Leads.rankedLeads, and MyLeads.byLane all read scoring.scoreOf(...), every weight tick ALSO re-sorts the full 80,814-feature Explore set and the Leads/MyLeads worklists. Undebounced; identical root cause to the filter-slider storm.
- **Grounded impact (real N):** ~20 ticks/drag → ~2.9M scorer ops (16,237 entries × 9-term sum) + ~20 full 80,814-row sorts for one weight drag. Tunable scoring is the Slice-C interaction the co-founder uses to re-rank the worklist live.
- **Expected gain:** ~20x fewer scoreById rebuilds and Explore/Leads re-sorts per weight drag; removes per-tick long tasks while tuning weights.
- **Execution (paste-back work order):** Mirror the FilterPanel fix: in ScoringPanel.svelte keep a local bound value per weight slider and debounce the scoring.setWeight commit (~120-160ms). Optionally memoize scoreById so it only recomputes when config.useDefault is false (in default mode effectiveScore returns the baked o.score). Keep extents as-is (depends only on once-loaded owners).
- **Behavior risk & rollback:** Blast radius: scoring weight UX + surfaces that rank by score (Explore list, Leads, MyLeads). Ranking updates on a short delay while dragging. Rollback: revert ScoringPanel to call setWeight directly. No persistence/preset-format change.
- **Suggested confirm-it measurement:** chrome-devtools performance trace while dragging a weight slider with Explore open; compare scripting time. Alt: console.time inside scoreById and count rebuilds per drag.
- **Merged from:** none (fe-compute #2).
- **Why this rank:** Same high-certainty ~20x pattern as PERF-002 on a core triage interaction; ranked just below it since weight-tuning is somewhat less frequent than filtering.

---

### PERF-004 — Code-split the 1.4MB single JS chunk — add manualChunks to isolate MapLibre + DuckDB glue as cacheable vendor chunks

**Rank 4**  ·  app/ frontend — bundle/delivery (vite build)  ·  _perceived_  ·  certainty 🟢 high  ·  effort ⚡ quick-win  ·  ✅ CONFIRMED (measured · local)

- **Location:** app/vite.config.ts:51-56 (build block sets only chunkSizeWarningLimit:1600, no rollupOptions); app/dist/assets/index-*.js (1,464,269 bytes — MapLibre + DuckDB glue + Svelte + all 25 components in ONE chunk)
- **What & why:** No manualChunks and zero dynamic imports in src/ (grep confirmed). MapLibre-GL (the dominant share of 1.4MB) and the @duckdb/duckdb-wasm glue are statically imported into the one entry chunk alongside all app code. Two costs: (1) every app-code edit re-hashes the whole 1.4MB chunk, busting the browser/edge cache for MapLibre+DuckDB too — bad for the co-founder reloading daily across the 4-week outcome-bar window with active deploys; (2) the browser can't parallelize download of vendor vs app code.
- **Grounded impact (real N):** 1,464,269-byte main chunk → 379KB gzip. Splitting lets the MapLibre+DuckDB vendor portion stay byte-identical across app deploys, served from cache on repeat visits instead of re-downloaded/re-validated.
- **Expected gain:** (estimate) Repeat-visit JS download drops from ~379KB gzip to the app-only delta (tens of KB) whenever only app code changes; vendor cached. Parallelized first-load download.
- **✅ Local validation — CONFIRMED (measured · local):** Real `manualChunks` build to a temp dir (zero repo files changed). Baseline single chunk = **1,464,269 B raw / 388,131 B gz**. After split: **app `index` chunk 178.8 KB raw / 51.4 KB gz (−88% raw, −87% gz)**; `maplibre` 1,027.7 KB / 273.0 KB gz; `duckdb` 193.8 KB / 45.2 KB gz; `vendor` 43.3 KB / 16.9 KB gz; `pmtiles` 18.2 KB / 7.2 KB gz. The MapLibre+DuckDB vendor bytes become separately-cacheable chunks the app-code rehash no longer busts. (Also split out a 69.8 KB MapLibre CSS chunk — see PERF-036.)
- **Execution (paste-back work order):** In vite.config.ts build block add `rollupOptions: { output: { manualChunks: { maplibre: ['maplibre-gl'], duckdb: ['@duckdb/duckdb-wasm'], pmtiles: ['pmtiles'] } } }`. Rebuild and confirm separate maplibre-*.js / duckdb-*.js chunks. Pairs with PERF-001 and PERF-012.
- **Behavior risk & rollback:** Build-only; runtime identical (same modules, more files). Rollback: delete rollupOptions. Vite handles chunk ordering + modulepreload automatically.
- **Suggested confirm-it measurement:** vite build + `du -h app/dist/assets/*.js` to confirm vendor chunks split out and the index chunk shrinks.
- **Merged from:** none (fe-perceived).
- **Why this rank:** High certainty, quick-win, repeat-visit benefit across the daily 4-week window — clear delivery win with near-zero risk.

---

### PERF-005 — Derive /api/counts from the persisted-lead set (and share nav passes) instead of three full 16,237-owner scans per nav refresh

**Rank 5**  ·  backend/app/owners_index_service.py (counts/list_candidates/list_my_leads) + main.py /api/counts /api/candidates /api/my-leads  ·  _compute_  ·  certainty 🟢 high  ·  effort ⚡ quick-win  ·  ✅ CONFIRMED (measured · local)

- **Location:** backend/app/owners_index_service.py:145 (list_candidates), :168 (list_my_leads), :195-209 (counts); backend/app/main.py:336-364
- **What & why:** counts() pulls the full effective owners list (16,237) and loops status_by_id.get(...) for EVERY owner just to produce {candidates, my_leads}. The two buckets partition the index, so the answer is fully determined by the tiny persisted-Lead set: my_leads = index owners whose persisted status != New; candidates = total - my_leads. Separately, a single nav typically fires /api/counts + a worklist, and counts/list_candidates/list_my_leads each do an independent O(16k) pass + status_map(). loadCounts() fires after every status change, pursue, attempt-log, merge, split, and on every Leads-view mount — the most frequently hit read.
- **Grounded impact (real N):** Every counts call iterates all 16,237 owners; a nav refresh does up to three separate full 16k passes. At production scale persisted leads are a tiny fraction of 16,237, so ~16k iterations are discarded on each of the most common interactions.
- **Expected gain:** counts becomes O(persisted_leads) (e.g. ~80x fewer iterations for a 200-worked-lead tenant; low-ms → sub-ms). Folding nav badges into the list responses' existing count fields removes one of three full passes per nav.
- **✅ Local validation — CONFIRMED (measured · local):** Over the real 40.9 MB / **16,237-owner** index: a single full counts-style pass = **~2.3 ms warm** (Python, fast dev CPU); a nav does up to three independent passes (~7 ms). Floor only — prod `shared-cpu-1x` is slower, and the gain (→ O(persisted leads)) grows as the owner count scales past the 4 anchor states.
- **Execution (paste-back work order):** In counts(): status_map = store.status_map(); my_leads = sum(1 for cid,s in status_map.items() if s != INITIAL_STATUS and cid in by_id); total = len(owners); return {'candidates': total-my_leads, 'my_leads': my_leads} (the `cid in by_id` guard preserves semantics + handles orphan leads). Under overrides build by_id once via effective(merges) and reuse — no second scan. Optionally have the client derive nav badges from CandidatesResponse.count / MyLeadsResponse.count instead of a third round-trip. Add a parity unit test (mix of New/off-New + an orphan lead id).
- **Behavior risk & rollback:** Blast radius: two nav badge integers + worklist counts. Off-by-one risk on orphan leads prevented by the guard; counts must stay exact (uncapped). Rollback: revert to the loop. Pure read; no schema change.
- **Suggested confirm-it measurement:** With .venv: load the real owners_index.json (16,237 owners) and timeit counts() old vs new against a seeded lead_state.sqlite3; confirm identical {candidates,my_leads} and the wall-time drop.
- **⚠️ Rail / dependency flag:** ADR-056 — keep effective() as the single resolver; this only changes how counts are sourced, not where resolution happens.
- **Merged from:** backend-read #19 + be-compute-auth #33 (three full 16k passes per nav; same counts/worklist redundant-scan root cause).
- **Why this rank:** Highest-frequency backend read (fires after every mutation), high certainty, quick-win — backend reads are HIGH weight and this one is felt after every triage action.

---

### PERF-006 — Add composite indexes on contact_attempt to kill the TEMP B-TREE filesort on the hot activity/lead-page reads

**Rank 6**  ·  backend/app/models.py (ContactAttempt) + db.py additive migration  ·  _compute_  ·  certainty 🟢 high  ·  effort ⚡ quick-win  ·  ✅ CONFIRMED (measured · local)

- **Location:** backend/app/models.py:52-78 (ContactAttempt — only single-column indexes on tenant_id and display_cluster_id); queries in backend/app/lead_store.py:43 (list_attempts), :54 (tenant_attempts), :65 (latest_flags), :85 (list_replies); db.py:58-63,93-106 (additive migration seam)
- **What & why:** ContactAttempt has only single-column indexes. EXPLAIN QUERY PLAN on the live dev DB confirms all hot read paths fall back to a temp B-tree sort: tenant_attempts (WHERE tenant_id ORDER BY occurred_on DESC, id DESC) → 'USE TEMP B-TREE FOR ORDER BY'; list_attempts (WHERE tenant_id AND display_cluster_id ORDER BY ...) → can use only one single-column index then filters + filesorts; latest_flags → same. The sort cost grows with the tenant's attempt count on every Dashboard/activity/stats/lead-page load.
- **Grounded impact (real N):** tenant_attempts() feeds /api/attention, /api/activity (twice today — see PERF-008), and /api/stats; list_attempts feeds every Lead-page open. Dev DB has 14 rows so the sort is free today, but the cost is structural: at production scale (thousands of attempts/tenant) every Dashboard render pays an O(m log m) in-memory sort a covering index makes O(log m + result).
- **Expected gain:** Eliminates the temp B-tree sort on all three queries; list_attempts gets a direct index range scan instead of tenant-wide scan + filter. EXPLAIN filesort line disappears (measurable).
- **✅ Local validation — CONFIRMED (measured · local):** `EXPLAIN QUERY PLAN` on the real dev DB: **both** `tenant_attempts` and `list_attempts` currently `USE TEMP B-TREE FOR ORDER BY`. After creating the two composite indexes on a **temp copy** (real DB untouched), the filesort **disappears** — `tenant_attempts` uses `(tenant_id, occurred_on, id)` and `list_attempts` resolves directly via `(tenant_id, display_cluster_id, occurred_on, id)`.
- **Execution (paste-back work order):** Declare on ContactAttempt: Index('ix_attempt_tenant_occurred','tenant_id','occurred_on','id') and Index('ix_attempt_tenant_cid_occurred','tenant_id','display_cluster_id','occurred_on','id'). Because create_all won't add indexes to an existing table, add CREATE INDEX IF NOT EXISTS in db.py alongside _migrate_added_columns (valid SQLite + Postgres). SQLite/Postgres scan ASC indexes backwards so DESC ordering is served. The single-column ix_contact_attempt_display_cluster_id becomes redundant — consider dropping. Re-run EXPLAIN to confirm.
- **Behavior risk & rollback:** Additive-only; no query results change, only the plan. Marginally slower writes (2 more indexes per insert) — negligible vs read frequency. Rollback: DROP INDEX.
- **Suggested confirm-it measurement:** sqlite3 on a copy of data/processed/lead_state.sqlite3, create the two indexes, re-run the captured EXPLAIN QUERY PLAN statements; confirm 'USE TEMP B-TREE FOR ORDER BY' disappears and list_attempts uses the cid composite.
- **⚠️ Rail / dependency flag:** Schema change rides the additive init_db migration until Alembic (CLAUDE.md §8); no tenant filtering relaxed (index leads with tenant_id).
- **Merged from:** backend-read #21 + be-compute-auth #30 (identical composite-index fix).
- **Why this rank:** High certainty, quick-win, backs the Lead page + three Dashboard endpoints — structural read win the co-founder feels at scale.

---

### PERF-007 — StatStrip 'Towers' count materializes the full deduped+sorted 80,814-row list just to read .length

**Rank 7**  ·  fe-compute / Explore derivation  ·  _compute_  ·  certainty 🟢 high  ·  effort ⚡ quick-win

- **Location:** app/src/components/StatStrip.svelte:13 (count = exploreTowers.count); app/src/lib/explore-towers.svelte.ts:19-30 (count = this.rows.length); app/src/lib/tower-list.ts:39-74 (rankedTowerRows builds Map + sorts)
- **What & why:** exploreTowers.count = this.rows.length, where rows is rankedTowerRows output — a dedup Map over all features AND a sort of survivors AND a TowerListRow allocation per survivor. The StatStrip Towers tile shows whenever Explore is open, so the full dedup + sort + row allocation over up to 80,814 features runs on every filter/score change purely to display one integer. The count needs only the number of distinct matching towers.
- **Grounded impact (real N):** Every filter or weight change forces a dedup Map insert over up to 80,814 features plus an O(n log n) sort just to render one number. Combined with PERF-002/003/010, multiplies per-interaction cost on the main triage screen.
- **Expected gain:** Removes the O(n log n) sort + ~80K object allocations from every count update; count becomes a single O(n) dedup-count pass.
- **Execution (paste-back work order):** Add a cheap `count = $derived.by(...)` in explore-towers.svelte.ts: iterate features, apply the shared matching/archived predicate, add cid+' '+asr to a Set, return set.size — no sort, no TowerListRow. Keep rows (sorted, materialized) for ExploreList only. Factor the keep-predicate so rows and count can't diverge. Point StatStrip at the new count.
- **Behavior risk & rollback:** Towers tile + Explore list share a derivation; keep one predicate so they agree. Rollback: revert to count = rows.length. No data changes.
- **Suggested confirm-it measurement:** chrome-devtools performance trace toggling a filter with the Explore candidates list collapsed but StatStrip visible; confirm the sort disappears from the flame chart. Alt: console.time around rankedTowerRows vs the new count pass.
- **Merged from:** none (fe-compute #3).
- **Why this rank:** High certainty, quick-win, on the triage screen — compounds with the debounce fixes on every filter/score change.

---

### PERF-008 — /api/activity scans contact_attempt twice and filters in Python — fetch once and push filters into SQL

**Rank 8**  ·  backend/app/activity_service.py + lead_store.py + main.py /api/activity  ·  _compute_  ·  certainty 🟢 high  ·  effort 🔧 small  ·  ✅ CONFIRMED (structural · local)

- **Location:** backend/app/activity_service.py:58-96 (events → tenant_attempts), :98-117 (digest → tenant_attempts AGAIN); backend/app/lead_store.py:54-63 (tenant_attempts); backend/app/main.py:870-918
- **What & why:** A single /api/activity request triggers TWO full tenant_attempts() scans: events() iterates once, digest() calls tenant_attempts() a second time and iterates again — each doing the TEMP B-TREE filesort (PERF-006). Worse, events() applies lead/member/channel/date_from/date_to filters in Python by looping every attempt and continue-ing, so the DB returns the tenant's entire history even when filtered to one lead or a one-week window.
- **Grounded impact (real N):** 2× full activity-history scans + filesorts per /api/activity load (History + Calendar both read this). With Python-side filtering, a date/lead/member filter still materializes every row before discarding — cost scales with total history, not the filtered result. Compounds with the per-row owner_name_of rebuild (PERF-009) for override tenants.
- **Expected gain:** Halves the scans (2→1) immediately; pushing filters to SQL makes a filtered query cost proportional to the result set (a 1-week filter over years returns weeks of rows, not all).
- **✅ Local validation — CONFIRMED (structural · local):** Code confirms `activity_service.py` calls `self.leads.tenant_attempts()` **twice** per `/api/activity` request — once in `events()` (:70) and again in `digest()` (:104) — each paying the PERF-006 filesort.
- **Execution (paste-back work order):** (1) Fetch tenant_attempts() once in the route (or have ActivityService accept the prefetched list / a @cached_property memo) and pass to both events() and digest(); digest is a cheap reduction over the same list — or compute the digest inline during the single events() pass. (2) Add an optional filtered LeadStore query (tenant_attempts(lead=,member=,channel=,date_from=,date_to=)) applying predicates as WHERE clauses; move _EXCLUDED_CHANNELS='dismiss' into SQL as channel != 'dismiss'. Note digest needs the unfiltered recent stream — keep the unfiltered fetch for digest, a separately-filtered query for events. Keep newest-first ordering.
- **Behavior risk & rollback:** Output identical; only the data path changes. Keep tenant_id in every new query (ADR-055). Mirror Python filter semantics exactly (channel equality, inclusive date bounds) and unit-test. Rollback: revert to two tenant_attempts() calls + Python filtering.
- **Suggested confirm-it measurement:** Spy/count LeadStore.tenant_attempts and hit GET /api/activity once with AUTH_DEV_MODE=1; assert called once. EXPLAIN QUERY PLAN the new filtered query; assert events()/digest() output unchanged on a fixture across each filter dimension.
- **⚠️ Rail / dependency flag:** ADR-055 tenant-scoped — new filtered query keeps tenant_id filter.
- **Merged from:** backend-read #23 + be-compute-auth #28 (duplicate tenant_attempts scan; #23 adds SQL filter push-down).
- **Why this rank:** High certainty, halves a hot Dashboard read + makes filters cheap at scale; backend read, felt on History/Calendar.

---

### PERF-009 — Memoize OwnersIndexService.effective() and add a single-owner fast path so reads stop rebuilding the full 16k merged index per call when overrides exist

**Rank 9**  ·  backend/app/owners_index_service.py (effective/get_owner/lead_view) + main.py read routes  ·  _compute_  ·  certainty 🟢 high  ·  effort 🔧 small  ·  ✅ CONFIRMED (measured · local)

- **Location:** backend/app/owners_index_service.py:57-77 (effective), :79-134 (_merge_group), :136-143 (get_owner), :211-267 (lead_view); backend/app/main.py:379-414 (update_lead), :466-513 (pursue/merge), :870-918 (/api/activity owner_name_of), :701 (/api/attention)
- **What & why:** When a tenant has ≥1 manual merge override, effective() iterates all 16,237 owners, groups by resolved root, runs _merge_group per group, and re-sorts all 16k by score — on EVERY call, no memoization. get_owner() and lead_view() both call effective(), so a single-owner lookup rebuilds + re-sorts the whole index. Routes amplify: update_lead does ~3 rebuilds, merge ~4. Worst: /api/activity and /api/attention pass owner_name_of=lambda cid: get_owner(cid,merges)..., invoked once PER row → O(rows × 16,237) + one 16k re-sort per row. No-override tenants hit the cheap cached fast-path. Manual merge/split is a shipped feature (#53) the primary user is likely to use.
- **Grounded impact (real N):** Gated on ≥1 override. When it triggers: each get_owner/lead_view = a full 16,237-owner regroup + sort. /api/activity for N rows = N full rebuilds; at N=5,000 that is ~8×10^7 owner touches + 5,000 sorts of 16k on one request. update_lead/merge do 3-4 redundant rebuilds each.
- **Expected gain:** Collapses M per-row full rebuilds to ONE per request: O(M·N·logN) → O(N·logN + M) (~200× fewer for a 200-row activity feed). Single-owner get_owner becomes O(group size) instead of O(16k log 16k).
- **✅ Local validation — CONFIRMED (measured · local):** Over the real 16,237-owner index, an `effective()`-style full regroup+index = **~10.8 ms/call** — and `get_owner()`/`lead_view()` pay this whole O(16k) cost to return **one** owner when ≥1 override exists. On an N-row activity feed the per-row `owner_name_of` lambda multiplies it (≈N × 10.8 ms before memoization).
- **Execution (paste-back work order):** (1) Memoize the merged (merged_list, by_id) on the request-scoped OwnerMergeService keyed on the override-map signature; clear it in OwnerMergeService._invalidate() alongside _map (so merge/split writes invalidate). Or route-local: in activity()/attention() call owners, by_id = effective(merges) once and close owner_name_of over by_id.get(merges.resolve(cid)). (2) get_owner(cid,merges): root=merges.resolve(cid); if len(merges.members_of(root))==1 return _by_id.get(root) directly; only _merge_group root's members otherwise — never regroup/sort the whole index for one lookup. Keep effective() for genuine list endpoints. Tests: identical output vs current under a 3-way merge; fast path matches.
- **Behavior risk & rollback:** Touches the single resolution chokepoint — keep _merge_group as the one merge implementation; do not fork resolution per surface or bake overrides into parquet. Stale-memo risk mitigated by keying on exact omap contents + invalidating on write. Rollback: drop cache + fast path.
- **Suggested confirm-it measurement:** With .venv: seed 2-3 owner_cluster_override rows; timeit get_owner() and a simulated /api/activity owner_name_of loop over the real 16,237-owner index before/after; assert byte-identical merged owner output and that effective()/_merge_group rebuilds once, not per-row.
- **⚠️ Rail / dependency flag:** ADR-056 single-place coalesce — memoizes/short-circuits only; _merge_group stays the sole merge implementation, overrides never baked into parquet.
- **Merged from:** backend-read #20 + be-compute-auth #29 (effective() rebuild per call + per-row owner_name_of amplification; same memoize fix).
- **Why this rank:** High certainty + very large when triggered, on the Lead-page / activity hot path; ranked below always-on reads because it is override-gated.

---

### PERF-010 — Every filter change rebuilds an 80,814-feature GeoJSON and re-ingests/re-clusters it via MapLibre setData (no no-op guard)

**Rank 10**  ·  fe-compute / map tower layer  ·  _compute_  ·  certainty 🟡 medium  ·  effort 🔧 small

- **Location:** app/src/components/MapView.svelte:481-500 (syncTowerLayers → filterTowers → src.setData), :582-589 ($effect tracks matchingClusterIds); app/src/lib/towers.ts:111-126 (filterTowers allocates a new FeatureCollection)
- **What & why:** syncTowerLayers calls filterTowers(app.towerPoints, matchingClusterIds, archived) then src.setData(data). filterTowers allocates a new FeatureCollection scanning all features, and setData forces MapLibre to re-parse, re-index, and RE-CLUSTER the entire clustered point set. This is the dominant cost term in the filter cascade, on every matchingClusterIds change. No no-op guard: when no filter is active filterTowers returns the same fc reference but setData still re-clusters 80K points; and a new Set identity each tick (PERF-002) fires the effect even when the feature set is unchanged.
- **Grounded impact (real N):** Up to 80,814 points re-clustered per filter change. Clustering is the heaviest single step MapLibre does on setData; at the un-debounced ~20 ticks/drag this is ~20 full re-clusterings of 80K points per slider drag.
- **Expected gain:** Skipping setData when the filtered result is reference- or content-equal to the last applied set eliminates redundant re-clusterings on no-op changes; with the PERF-002 debounce, drops from ~20 re-clusters/drag to 1.
- **Execution (paste-back work order):** In MapView.svelte cache the last FeatureCollection passed to setData and skip src.setData when filterTowers returns the identical reference (null/unfiltered fast path already returns the same fc) or when the new feature count + a cheap signature is unchanged. Land PERF-002 first. Keep clustering semantics — setData remains the mechanism; this only removes redundant calls. (If cluster counts need not reflect the filter, an alternative is setFilter on an unclustered point layer — but confirm desired behavior first.)
- **Behavior risk & rollback:** Tower layer rendering only. A stale guard could skip a needed update — gate strictly on reference/identity equality. Rollback: always call setData. No data changes.
- **Suggested confirm-it measurement:** chrome-devtools performance trace dragging a filter slider; look for repeated MapLibre worker/cluster activity and confirm it collapses after the guard + PERF-002.
- **Merged from:** fe-compute #4 + fe-perceived #14 (filterTowers full rebuild + re-cluster on every filter change; same setData no-op-guard fix).
- **Why this rank:** Dominant cost on the hot filter path; medium certainty (re-cluster ms is estimate-only) keeps it just below the high-certainty interaction fixes it pairs with.

---

### PERF-011 — Eliminate 80,814 main-thread SHA-1 owner-key hashes computed at boot in rowsToFeatureCollection

**Rank 11**  ·  app/ frontend — boot CPU (tower ingest)  ·  _perceived_  ·  certainty 🟢 high  ·  effort 🔧 small

- **Location:** app/src/lib/towers.ts:78-97 (rowsToFeatureCollection calls ownerNameToClusterId per row, line 89), :133-145 (loadTowerPoints); app/src/lib/owner-cluster.ts:29-50,57-120 (normalizeOwnerName + hand-rolled sha1Hex); duckdb.ts:190-198 (SELECT)
- **What & why:** For every tower row DuckDB returns, the app computes cid = ownerNameToClusterId(owner): a normalize pass (uppercase + 3 regex replaces + split/sort/join) followed by a full synchronous SHA-1, on the main thread. The comment claims cid is 'precomputed once' — it is, but per session in JS rather than baked into the data, blocking first interactivity on every cold load.
- **Grounded impact (real N):** 05=15,789 + 12=53,010 + 30=4,685 + 54=7,330 = 80,814 synchronous SHA-1 hashes + regex normalizations on the main thread during the structures-first map load, every cold load.
- **Expected gain:** (estimate) Removes ~80K SHA-1 + regex ops from boot (tens-to-low-hundreds of ms scripting); eliminated entirely if baked server-side, or moved off the main thread via a worker.
- **Execution (paste-back work order):** Preferred (B): bake display_cluster_id as a column in each state's towers.parquet at preprocess time using the SAME Python cluster.normalize_owner_name + owners_index.display_cluster_id, then `CAST(display_cluster_id AS VARCHAR) AS cid` in duckdb.ts:190-198 and read it straight through, dropping the ownerNameToClusterId call. The key is the RAW name-anchored cluster id (identical to today's client output), NOT the override-resolved display id. Lower-effort frontend-only (A): move the cid hashing into a Web Worker or chunk it with scheduler.postTask so it doesn't block first paint.
- **Behavior risk & rollback:** tower→Lead linking relies on cid parity with the Python pipeline (owner-cluster.ts is pinned byte-for-byte by tests/unit/owner-cluster.test.ts; backend looks up Leads by exactly this id). Option B MUST be produced by the same Python function or Lead pages 404. Option A has no parity risk. Rollback: keep computing cid in JS.
- **Suggested confirm-it measurement:** console.time around rowsToFeatureCollection at boot over the real 80,814 rows; or a chrome-devtools boot performance trace looking for the long task during tower load.
- **⚠️ Rail / dependency flag:** Option B touches preprocess towers.parquet schema (cross-lane): additive column only, EPSG:4326 + no-normalize-filter rails untouched; must reuse the existing Python cluster function (owner-cluster parity rail) and keep raw cluster ids untouched so overrides survive recompute. No new dependency.
- **Merged from:** fe-compute #5 + fe-perceived #11 (identical SHA-1-at-boot finding).
- **Why this rank:** High-certainty boot CPU win on the path to first usable screen; ranked below PERF-001 since PERF-001 already defers this off the landing path (this removes it from the first-Explore path too).

---

### PERF-012 — Lazy-load route-only components (LeadPage, Settings + subpages, Tasks, Calendar, Dashboard, Leads) via dynamic import

**Rank 12**  ·  app/ frontend — bundle/delivery (route components)  ·  _perceived_  ·  certainty 🟢 high  ·  effort 🔧 small

- **Location:** app/src/App.svelte:6-16 (static imports), :317-325 + :332-344 (render sites); off-first-paint: LeadPage.svelte (897 lines), TowerDetail.svelte (461), Tasks.svelte (413), Dashboard.svelte (309), MyLeads.svelte (298), Stats.svelte (281), Calendar.svelte (248), Settings.svelte (122) + children
- **What & why:** All 25 components are statically imported, so they all land in the one 1.4MB chunk even though only one section renders at a time and several (Settings + SettingsAccount/Appearance/Filters/Automations, Tasks, Calendar, LeadPage) are reached only via explicit navigation — never on first paint. Dead weight in the critical-path bundle.
- **Grounded impact (real N):** src/components totals 6,329 lines; the off-first-paint route components (LeadPage 897, TowerDetail 461, Tasks 413, Dashboard 309, MyLeads 298, Stats 281, Calendar 248, Leads 196, History 188, the 5 Settings* files) are ~3,800 of those lines compiled into the first-paint chunk.
- **Expected gain:** (estimate) Trims the main entry chunk by the compiled size of those components, shrinking parse/compile on first load; each becomes its own on-demand chunk.
- **Execution (paste-back work order):** In App.svelte replace static imports of section components with a lazy wrapper using `{#await import('./components/Settings.svelte') then mod}<mod.default .../>{/await}` (or a tiny lazy.svelte helper) at the render sites (:332-344 Settings/Dashboard/Leads/LeadPage; :317-325 Explore overlay ExploreList/TowerDetail). Keep MapView/FilterPanel/StatStrip/DetailsPanel eager (Explore shell). Requires PERF-004 manualChunks to be effective.
- **Behavior risk & rollback:** Adds a tiny async boundary when first opening Settings/Lead/Tasks (one-time). Rollback: restore static imports. Ensure the {#await} fallback doesn't flash (render nothing/skeleton while pending).
- **Suggested confirm-it measurement:** vite build + compare index chunk byte size before/after; confirm new per-route chunks in dist/assets.
- **Merged from:** none (fe-perceived).
- **Why this rank:** High certainty delivery win; ranked below the headline cold-load + interaction fixes since most savings overlap with PERF-001's deferral.

---

### PERF-013 — 10.89MB owners_filter.json (16,237 owners) JSON.parsed + object-mapped on the main thread at boot

**Rank 13**  ·  app/ frontend — boot data (owners filter index)  ·  _perceived_  ·  certainty 🟢 high  ·  effort 🔧 small  ·  ✅ CONFIRMED (measured · local)

- **Location:** app/src/lib/owners-filter-index.ts:60-77 (fetch → res.json() → .map(toRecord)); triggered by app/src/components/FilterPanel.svelte:18 (onMount, always-mounted sidebar)
- **What & why:** FilterPanel mounts as part of the always-rendered Explore sidebar, so filterModel.load() fires at boot even on the Dashboard. gzip handles the wire (10.6MB → 722KB) but the browser still JSON.parses the full 10.6MB body and allocates 16,237 fully-typed 20-field records via .map(toRecord) on the main thread. The parse+allocate is the real cost.
- **Grounded impact (real N):** owners_filter.json = 10.89MB / 16,237 owners (measured). JSON.parse of 10.6MB + 16,237 object allocations on the UI thread on every cold load.
- **Expected gain:** (estimate) Removes a 10.6MB parse + 16K-object allocation from boot (commonly 100s of ms of main-thread block).
- **✅ Local validation — CONFIRMED (measured · local):** Network capture: `owners_filter.json` = **10,637 KB transferred ≈ 10,636 KB decoded** on the Dashboard landing — i.e. served **uncompressed** in this local preview (informs PERF-019). For parse scale, the sibling 40.9 MB `owners_index.json` cold-parses in **231 ms**; the 10.6 MB filter JSON's main-thread `JSON.parse` + 16,237 object allocations is the standing cost regardless of wire compression.
- **Execution (paste-back work order):** Three options, increasing payoff: (a) cheapest — drop FilterPanel.svelte:18 onMount load and trigger filterModel.load() only when the filter panel is first interacted with / Explore first shown (pairs with PERF-001); (b) parse off the main thread in a Web Worker; (c) ship owners_filter as parquet read through the existing DuckDB engine (same HTTP-range pattern), eliminating the 10.6MB JSON.parse and enabling column projection — rewrites filter-model derived scans into queries (larger).
- **Behavior risk & rollback:** loadOwnersFilterIndex is already tolerant of missing fields; a parquet variant must preserve safe-default tolerance and not bake overrides in. Rollback: keep JSON. Option (c) is the larger rewrite.
- **Suggested confirm-it measurement:** console.time around loadOwnersFilterIndex in dev; chrome-devtools boot performance trace showing the parse block.
- **⚠️ Rail / dependency flag:** OWNERS_INDEX_SCHEMA_VERSION rail — any parquet variant must keep safe-default tolerance and leave resolution in OwnersIndexService.effective. No new dependency for (a)/(b).
- **Merged from:** none (fe-perceived #12). Overlaps PERF-001 on the landing path.
- **Why this rank:** High-certainty boot win, but option (a) overlaps with PERF-001's deferral; the deeper parse/parquet fix is the standalone value here.

---

### PERF-014 — Solar GeoJSON (~2.7MB, FL=2.2MB) downloaded + parsed at boot although the solar layer is hidden by default

**Rank 14**  ·  app/ frontend — boot data (solar context layer)  ·  _perceived_  ·  certainty 🟢 high  ·  effort ⚡ quick-win  ·  ✅ CONFIRMED (measured · local)

- **Location:** app/src/lib/stores.svelte.ts:129-130,171-184 (boot kicks off loadSolar unconditionally); app/src/lib/solar.ts:71-83 (loadSolarPoints), :89 (showSolarLayer false unless filter includes 'solar'); app/src/components/MapView.svelte:336-359 (addSolarLayer adds source even when visibility:'none'), :570-578 (solar $effect)
- **What & why:** Solar is a context layer hidden unless the Structure-type filter explicitly includes 'solar' (off by default). Yet boot eagerly probes and downloads every anchor state's solar_facilities.geojson, parses it, merges into one FeatureCollection, and adds it to the map with visibility:'none'. Pure waste for the default view.
- **Grounded impact (real N):** Solar GeoJSON on disk: FL=2.2MB, AR=356KB, MT=100KB, WV=88KB ≈ 2.74MB raw (~750KB gzip), all fetched + JSON-parsed at boot for a layer that renders nothing by default.
- **Expected gain:** Removes ~2.7MB download + parse from boot for the common case (~0.7MB gzip wire + parse saved per cold load).
- **✅ Local validation — CONFIRMED (measured · local):** Network capture: solar GeoJSON fired on the Dashboard landing for all anchors — **FL 2,228 + AR 354 + MT 97 + WV 86 = ~2.77 MB** — for a layer hidden by default.
- **Execution (paste-back work order):** In stores.svelte.ts don't call loadSolar() in boot(); trigger it the first time showSolarLayer(filterModel.model) becomes true. In the MapView solar $effect (MapView.svelte:570-578) call app.loadSolar() guarded by showSolarLayer and let addSolarLayer run once data arrives. solarTotal()/the Solar stat tile uses index counts (stores.svelte.ts:83), not the GeoJSON, so the badge is unaffected.
- **Behavior risk & rollback:** First time solar is enabled, dots appear after a short fetch (consistent with other lazy layers). Rollback: restore the boot loadSolar() call.
- **Suggested confirm-it measurement:** list_network_requests at boot to confirm solar_facilities.geojson no longer fires until solar is enabled in the filter.
- **Merged from:** none (fe-perceived #13). Overlaps PERF-001.
- **Why this rank:** High-certainty quick-win; overlaps PERF-001 deferral but is a clean standalone lazy-load with its own merit.

---

### PERF-015 — Vectorize interestingness scoring — replace the per-row DataFrame.apply over EVERY parcel with column math

**Rank 15**  ·  preprocess (per-chunk interestingness annotator)  ·  _compute_  ·  certainty 🟢 high  ·  effort 🏗️ larger refactor  ·  ✅ MEASURED — impact TEMPERED (local)

- **Location:** scripts/preprocess/annotators/interestingness.py:20-30; scripts/preprocess/scoring.py:59-104 (compute_components/_get) + 155-195 (apply_weights)
- **What & why:** interestingness.annotate runs parcels.apply(compute_components, axis=1) (row-wise Python over every parcel), then .apply(apply_weights), then THREE more .apply passes. compute_components calls _get() (try/except dict lookup) ~12 times per row and builds a ScoreComponents dataclass per row. Classic pandas anti-pattern, in the main chunk loop on ALL parcels. Inputs are already materialized columns and the scoring is pure threshold arithmetic — fully vectorizable.
- **Grounded impact (real N):** Runs on every parcel of every state (FL ~11M, AR ~2.1M, MT ~0.9M). At ~11M rows: ~5 full-frame .apply passes + ~130M try/except lookups + ~11M dataclass allocations — plausibly the single largest CPU sink in the per-chunk path and a direct contributor to the ~1,710 rows/s ceiling.
- **Expected gain:** Vectorized column math is typically 20-100x faster than axis=1 apply; the interestingness step likely drops from minutes to seconds per large state. Biggest single compute win in this lane.
- **✅ Local validation — MEASURED — impact TEMPERED (local):** Surgical benchmark over real MT parcels (no recompose, no writes): `interestingness.annotate` runs at **~62,877 rows/sec** in isolation — *faster* than the documented ~1,710 rows/sec **whole-pipeline** throughput. So the 5× row-wise `.apply` is genuine waste but only **~3% of MT compose wall-clock** (~15 s of a ~9 min job over 920,111 MT parcels). Vectorizing is still correct, but it is **not** the dominant ETL cost — treat the 'minutes→seconds, biggest single compute win' framing as the *scoring step's own* speedup, not a proportional pipeline win.
- **Execution (paste-back work order):** Rewrite compute_components/apply_weights to operate on the frame: numpy/boolean Series for infra_types, max_infra_instances (np.maximum.reduce of the three counts), overlays, arc_tier (distress_tier.str.lower()), owner_kind, cluster_size; apply weights with np.where/Series ops; clip to [0,1]; round. Keep DEFAULT_PROFILE byte-identical. Assemble the two dict columns (interestingness_components, _raw) once from the computed Series rather than per-row .to_dict(). Keep the pure-row compute_components(row) for the TS-parity/unit-test path but stop using it in the hot loop.
- **Behavior risk & rollback:** Must reproduce the legacy score + breakdown EXACTLY (parquet output + the app's live re-scorer depend on it — ADR-058). Assert old==new on a sample frame before deleting the apply path. Revert is a two-file diff; existing scoring unit tests guard apply_weights.
- **Suggested confirm-it measurement:** `python scripts/preprocess.py --state 30` before/after, then diff interestingness_score + interestingness_components columns of the MT parcels parquet for exact equality; compare chunk-loop wall-clock.
- **⚠️ Rail / dependency flag:** none — keeps EPSG:4326 + ADR-058 score parity; no new deps.
- **Merged from:** none (preprocess #37).
- **Why this rank:** High certainty + very large magnitude (20-100x) on the slowest ETL stage; ranked mid-pack because it is dev-side batch (MED lane) — nobody waits on it during triage.

---

### PERF-016 — Collapse the per-infra-layer parcel-shard rescans (towers + solar each re-read every parcel shard) into one shard pass

**Rank 16**  ·  preprocess (compose / infra→parcel pre-pass)  ·  _compute_  ·  certainty 🟢 high  ·  effort 🔧 small

- **Location:** scripts/preprocess/compose.py:120-173 (_build_infra_to_parcel_lookup) called 3x at compose.py:237-257
- **What & why:** compose() calls _build_infra_to_parcel_lookup once per infra layer (tower, solar, billboard). Each call independently iterates iter_state_parcel_shards(state_fips), gpd.read_parquet's every shard (full geometry), filters validity, builds a fresh STRtree, and sjoins. The shard set + parcel geometry are identical across calls — only the small infra layer differs — so the largest dataset is read, parsed, and spatially indexed N times. Every anchor state ships non-empty towers AND solar (billboard absent → 3rd call early-returns), so this is 2 full redundant geometry passes per state today, 3 once billboards land.
- **Grounded impact (real N):** Parcel geometry is the heaviest data in the ETL (FL ~11M; AR ~2.1M; MT ~0.9M; ~1,710 rows/s). For FL the shards are read + GEOS-validated + STRtree-built twice over ~11M polygons purely for the infra pre-pass; collapsing removes one entire ~11M-parcel sweep per state — a dominant cost feeding the memory wall / slow compose.
- **Expected gain:** ~1 full parcel-geometry pass eliminated per anchor state today (≈ -33% of the infra pre-pass disk read + STRtree builds; towers+solar 2 sweeps → 1), rising to -50% once billboards exist.
- **Execution (paste-back work order):** Refactor into a single-pass driver build_infra_to_parcel_lookups(specs, state_fips) where specs = {'tower': (ctx.get('tower'), keep_cols_t), 'solar': (ctx.get('solar_facility'), keep_cols_s), ...}. Open ONE `for label, chunk in iter_state_parcel_shards(state_fips)` loop; prepare the valid-parcel right frame once, run gpd.sjoin against each non-empty infra layer, accumulate into {name: {row_idx: attach}}. Drop None/empty layers before the loop. Update compose.py:237-257 to call once and unpack tower_lookup/solar_lookup/billboard_lookup. Keep first-match-wins (setdefault) per layer; keep each layer's own keep_cols rename map.
- **Behavior risk & rollback:** Output identical (same per-infra-row attaches, first-match-wins). One private helper + its single call site; revert is a one-file diff.
- **Suggested confirm-it measurement:** time one county via `python scripts/preprocess.py --state 30` (MT) before/after; confirm summary.json counts + carrier_coverage unchanged and wall-clock drops on the infra→parcel sjoin pre-pass log lines.
- **Merged from:** none (preprocess #36).
- **Why this rank:** High certainty, -33% of the parcel pre-pass; dev-side batch (MED lane) keeps it just below the headline user-facing wins but high among ETL.

---

### PERF-017 — Stop allocating 16,237 LeadRow objects on every /api/stats call by precomputing static per-state/owner counts

**Rank 17**  ·  backend/app/main.py (/api/stats) + stats_service.py + owners_index_service.py  ·  _compute_  ·  certainty 🟡 medium  ·  effort 🏗️ larger refactor

- **Location:** backend/app/main.py:812-866 (stats route, leads comprehension 828-835); backend/app/stats_service.py:67-172 (compute/_funnel/_by_state)
- **What & why:** The /api/stats route builds one LeadRow per owner in the entire index — leads = [LeadRow(cid, states=list(o.get('states') or []), status) for o in owners] — i.e. 16,237 dataclass instances + 16,237 list() copies of states, on every stats request, regardless of filters. StatsService then does ≥3 full passes over that list. The vast majority are untouched 'new' candidates whose per-row identity is never needed — only aggregate counts are.
- **Grounded impact (real N):** 16,237 LeadRow allocations + 16,237 states-list copies + ≥3 full 16k passes per /api/stats load (Dashboard Stats tab), independent of the date filter. Every Stats view is dominated by rebuilding the same 16k-owner skeleton that never changes between requests.
- **Expected gain:** Removes ~16K allocations + states copies per call; funnel/by_state 'new' bucket becomes O(1)/O(states) from a precomputed table. Stats compute falls from owner-count-bound to persisted-lead-bound.
- **Execution (paste-back work order):** Precompute once at index load (reload()): total_owners, per-state owner counts, per-state cid membership for the state filter. At request time the only dynamic input is the small off-New lead set (status_map). funnel = start {new: total_owners} (or per-state count when filtered) and reassign each persisted lead from 'new' to its actual status; _by_state overlays persisted leads on the static baseline. Feed StatsService aggregate baselines + the small persisted-lead delta rather than 16k rows; preserve member/state/date semantics + the reply_rate denominator. Parity tests vs the current full-list compute.
- **Behavior risk & rollback:** Stats numbers are user-facing. Keep merges applied (effective(merges) defines the population) and the state-filter membership exact; derive the baseline from the same effective() owners (cache under the no-override signature). Rollback: revert to the per-owner comprehension.
- **Suggested confirm-it measurement:** With .venv: timeit the stats route leads-comprehension + svc.compute() over the real 16,237-owner index before/after; assert identical StatsResult on a seeded DB across no-filter, state-filter, member-filter.
- **⚠️ Rail / dependency flag:** OWNERS_INDEX_SCHEMA_VERSION — any precomputed baseline must tolerate stale/missing fields; derive at load from existing fields, don't add schema fields.
- **Merged from:** none (backend-read #22).
- **Why this rank:** Backend read on the Dashboard Stats tab; medium certainty + larger refactor keep it below the high-certainty quick-wins.

---

### PERF-018 — favicon.png is 98.8KB — an oversized icon fetched on every page including the pre-auth sign-in gate

**Rank 18**  ·  app/ frontend — static asset  ·  _perceived_  ·  certainty 🟢 high  ·  effort ⚡ quick-win  ·  ✅ CONFIRMED (measured · local)

- **Location:** app/dist/favicon.png (98,887 bytes); app/public/favicon.png (Vite bundles public/ → /favicon.png); app/index.html:6 (<link rel="icon">)
- **What & why:** The favicon is a 98.8KB PNG — ~30-50x larger than needed. Referenced in index.html so the browser fetches it on the very first paint, even on the unauthenticated sign-in gate. Project memory explicitly says to keep this image small.
- **Grounded impact (real N):** 98,887 bytes on every initial page load (and re-fetched if not cached). A 32x32/48x48 icon is ~1-3KB.
- **Expected gain:** ~96KB saved per uncached load; trivial but free.
- **✅ Local validation — CONFIRMED (measured · local):** Network capture: `favicon.png` = **97 KB** fetched on first paint (including the pre-auth sign-in gate).
- **Execution (paste-back work order):** Re-export app/public/favicon.png at 48x48 (or a multi-size .ico / 32x32 PNG) optimized through pngquant/oxipng; keep the same /favicon.png path so index.html + Vite bundling are unchanged.
- **Behavior risk & rollback:** Cosmetic only. Rollback: restore the original PNG.
- **Suggested confirm-it measurement:** du -h app/public/favicon.png after re-export.
- **Merged from:** none (fe-perceived #17).
- **Why this rank:** High certainty, free, on first paint (incl. pre-auth) — small magnitude caps the rank.

---

### PERF-019 — Production serving: add immutable cache headers on hashed /assets/* and brotli — 34MB WASM + 1.4MB JS revalidate on every repeat visit

**Rank 19**  ·  deploy — edge serving (Caddy)  ·  _perceived_  ·  certainty 🟡 medium  ·  effort ⚡ quick-win

- **Location:** Caddyfile:19 (encode gzip — gzip only, no zstd/br); Caddyfile:52-56 (SPA handle sets no Cache-Control); app/dist/assets/* (Vite emits content-hashed immutable filenames)
- **What & why:** Vite emits content-hashed immutable filenames, but the SPA handler sets no Cache-Control, so Caddy serves only Etag/Last-Modified — every reload revalidates each asset with a 304 round-trip instead of a zero-RTT cache hit. .wasm is not in Cloudflare's default cached set, so the 34MB DuckDB binary is origin-served from shared-cpu-1x. And encode gzip (no brotli/zstd) leaves ~15-20% on the table. The co-founder reloads daily for 4 weeks, so repeat-visit cost compounds.
- **Grounded impact (real N):** Per repeat visit without immutable headers: revalidation round-trips for the 34MB (~7MB gzip) WASM, 1.4MB (379KB gzip) JS, ~1.6MB workers, 116KB (18KB gzip) CSS. brotli cuts the 379KB gzip JS to ~310KB and the 722KB gzip owners JSON to ~600KB.
- **Expected gain:** (estimate) Repeat-visit asset transfer → ~0 (304s eliminated) for hashed assets; first-load JS/JSON ~15-20% smaller with brotli.
- **Execution (paste-back work order):** In the Caddyfile SPA handle add `header /assets/* Cache-Control "public, max-age=31536000, immutable"` (only the hashed subtree — index.html stays revalidated). For brotli either `encode zstd gzip` (zstd built-in) or build Caddy with the brotli plugin (xcaddy). Validate with tests/test_caddy_serving.py, which boots this exact Caddyfile against fixtures.
- **Behavior risk & rollback:** Only touches /assets/* (content-hashed, non-PII) — does NOT touch /data/processed/* which must stay private, no-store (PII rail). Rollback: remove the header line. brotli plugin = a Caddy build change.
- **Suggested confirm-it measurement:** Boot the Caddyfile locally via tests/test_caddy_serving.py fixtures and curl -I an /assets/*.js to confirm Cache-Control + Content-Encoding. Do NOT deploy to prod (work order only).
- **⚠️ Rail / dependency flag:** Production serving — report/work-order only, do not deploy. PII rail respected (header scoped to /assets/*, /data/* stays no-store). brotli via plugin = NEW CADDY BUILD CAPABILITY (flagged); the immutable-header change needs no new dependency.
- **Merged from:** none (deploy #16).
- **Why this rank:** Repeat-visit win across the 4-week daily window; medium certainty + report-only/do-not-deploy posture lower the rank.

---

### PERF-020 — Vectorize geom_bbox construction (row-wise apply over all parcels at normalize time)

**Rank 20**  ·  preprocess (geometry derivatives, normalize)  ·  _compute_  ·  certainty 🟢 high  ·  effort ⚡ quick-win  ·  ✅ CONFIRMED (structural · local)

- **Location:** scripts/preprocess/geom.py:93-94 (add_polygon_derivatives)
- **What & why:** `gdf['geom_bbox'] = bounds.apply(lambda r: [r['minx'],r['miny'],r['maxx'],r['maxy']], axis=1)` builds a 4-element list per parcel via row-wise Python apply. gdf.geometry.bounds already returns a vectorized DataFrame; turning it into lists is one numpy round-trip with no per-row Python.
- **Grounded impact (real N):** add_polygon_derivatives runs at normalize time on every parcel layer of every parcel source (FL ~11M across 67 county layers; AR ~2.1M; MT ~0.9M). The axis=1 apply is ~11M Python lambda calls for FL on top of the necessary Albers reprojection + simplify.
- **Expected gain:** `bounds[['minx','miny','maxx','maxy']].to_numpy().tolist()` is ~50-100x faster for this column; shaves seconds-to-minutes off normalize for large states.
- **✅ Local validation — CONFIRMED (structural · local):** Code confirms `geom.py:94` builds `geom_bbox` via `bounds.apply(..., axis=1)` — a row-wise Python lambda over every parcel; `gdf.geometry.bounds` is already vectorized.
- **Execution (paste-back work order):** Replace lines 93-94 with: `b = gdf.geometry.bounds; gdf['geom_bbox'] = b[['minx','miny','maxx','maxy']].to_numpy().tolist()`. Same list-of-4-floats per row, order preserved. No change to centroid/area/simplify.
- **Behavior risk & rollback:** Identical values/order; keep float64 (already is). One-line revert. geom_bbox is later JSON-encoded by io._prep_complex_cols which expects a list — preserved.
- **Suggested confirm-it measurement:** `python scripts/preprocess.py --state 30` (or time one county); diff geom_bbox of a normalized shard for equality.
- **Merged from:** none (preprocess #38).
- **Why this rank:** High certainty quick-win on every parcel at normalize; dev-side batch caps it mid-pack.

---

### PERF-021 — Hoist county_score rollup out of the per-shard loop (prepare() recomputed on every parcel shard)

**Rank 21**  ·  preprocess (per-chunk joins / county score)  ·  _compute_  ·  certainty 🟢 high  ·  effort ⚡ quick-win

- **Location:** scripts/preprocess/per_chunk_joins.py:58-64 (apply_county_score) invoked per chunk at compose.py:318
- **What & why:** apply_county_score calls county_score.prepare(scores) for EVERY parcel shard. prepare() does a groupby('county_fips').agg over the county_score table — small and identical for the whole state — so the same rollup is recomputed once per shard. The annotate step legitimately runs per chunk; only the prepare() rollup is redundant (the annotator docstring even flags 'a caller may hoist it once').
- **Grounded impact (real N):** FL composes ~67 county shards, so the county_score rollup runs ~67x per FL build instead of once (fewer for AR/WV/MT). Small absolute cost but pure repeated work on the hot path with a trivial fix.
- **Expected gain:** N_shards → 1 county_score rollups per state (~67x → 1x for FL). Small absolute ms, zero risk.
- **Execution (paste-back work order):** In compose.py, before the iter_state_parcel_shards loop compute `county_score_prepared = county_score.prepare(ctx.get('county_score'))` once. Add an apply_county_score variant (or param) that takes the prepared frame and calls only county_score.annotate(chunk, county_score_prepared). Replace the per-chunk apply_county_score(chunk, ctx.get('county_score')) call.
- **Behavior risk & rollback:** prepare() is deterministic + chunk-independent (docstring), so output unchanged. compose.py loop + one helper signature; easy revert.
- **Suggested confirm-it measurement:** `python scripts/preprocess.py --state 30`; confirm distress_tier/persistent_poverty columns in MT parcels are byte-identical; estimate-only on timing.
- **Merged from:** none (preprocess #39).
- **Why this rank:** High certainty zero-risk quick-win; small absolute magnitude + batch lane place it here.

---

### PERF-022 — Collapse lead_view's per-merged-member attempt queries into one IN-query

**Rank 22**  ·  backend/app/owners_index_service.py (lead_view) + lead_store.py  ·  _compute_  ·  certainty 🟡 medium  ·  effort ⚡ quick-win

- **Location:** backend/app/owners_index_service.py:227-241 (members loop, attempts comprehension at 233); backend/app/lead_store.py:43-52 (list_attempts)
- **What & why:** lead_view builds attempts via [a for m in members for a in store.list_attempts(m)] — one SQL query per merged member (query-in-loop), then re-sorts the concatenation in Python. members_of(root) also calls merges.resolve(source) per override row (O(overrides^2)). Without merges this is a single query; the N+1 appears for merged owners.
- **Grounded impact (real N):** Bounded by merge-group size (small today) but on the Lead-page hot path (opened per lead worked), and each member query repeats the contact_attempt filesort (PERF-006). For a heavily-merged owner the queries multiply linearly.
- **Expected gain:** 1 query instead of len(members) for the Lead page; removes the Python re-sort if the single query orders by (occurred_on DESC, id DESC).
- **Execution (paste-back work order):** Add LeadStore.list_attempts_for(cluster_ids: set[str]) issuing one SELECT ... WHERE tenant_id=? AND display_cluster_id IN (:ids) ORDER BY occurred_on DESC, id DESC; call once with members in lead_view. Lets the DB do the ordering (no Python sort) and benefits from the PERF-006 (tenant_id, display_cluster_id, occurred_on, id) composite. Chunk the IN-list for pathologically large groups.
- **Behavior risk & rollback:** Output identical (same rows, same order). Keep tenant_id in the IN-query (ADR-055). Rollback: revert to the comprehension.
- **Suggested confirm-it measurement:** EXPLAIN QUERY PLAN the IN-query on lead_state.sqlite3; assert lead_view attempts output identical on a fixture with a 3-member merge.
- **⚠️ Rail / dependency flag:** ADR-055 tenant scoping — IN-query keeps tenant_id filter.
- **Merged from:** none (backend-read #27).
- **Why this rank:** Lead-page hot path, but modest magnitude (small merge groups today) + medium certainty.

---

### PERF-023 — Push the auto-followup status filter into SQL and index task ordering

**Rank 23**  ·  backend/app/task_store.py + auto_followup_rule.py + models.py  ·  _compute_  ·  certainty 🟡 medium  ·  effort 🔧 small

- **Location:** backend/app/auto_followup_rule.py:70 (cancel_on_reply), :77 (_has_open_auto via TaskStore.list_filtered); backend/app/task_store.py:69 (list), :173 (list_filtered, ORDER BY created_at DESC, id DESC); models.py:160-196 (Task — only single-column indexes)
- **What & why:** (1) _has_open_auto() calls list_filtered(lead_cluster_id=cid, source='auto') then filters status != done in Python (auto_followup_rule.py:77-81), loading every auto task for the lead just to test existence; cancel_on_reply does the same load+Python-filter. The 'is there an open auto follow-up?' check should be a status-filtered EXISTS/COUNT in SQL. These run on the write hot path (PUT /api/leads status→contacted, and POST attempts on every outbound touch). (2) TaskStore.list()/list_filtered() ORDER BY (created_at DESC, id DESC) has no supporting index — EXPLAIN shows 'SEARCH task USING ix_task_tenant_id' + 'USE TEMP B-TREE FOR ORDER BY'.
- **Grounded impact (real N):** Auto follow-up fires on every contacted-transition + every outbound touch (#116 shipped, on by default), so these run on the outreach write path the co-founder hits all day. task table grows with manual + auto tasks; the unindexed sort is paid on every GET /api/tasks. Dev has 1 task — structural at production counts.
- **Expected gain:** _has_open_auto: 'hydrate all auto tasks for lead' → single indexed COUNT/EXISTS. GET /api/tasks: removes the TEMP B-TREE filesort via a (tenant_id, created_at, id) composite index.
- **Execution (paste-back work order):** (1) Add TaskStore.has_open(lead_cluster_id, source) -> bool using select(func.count()).where(tenant_id, lead_cluster_id, source, status != DONE_STATUS).limit(1); have _has_open_auto call it instead of list_filtered+Python filter; add a cancel helper so cancel_on_reply deletes via a tenant+lead+source+status!=done query. (2) Declare Index('ix_task_tenant_created','tenant_id','created_at','id') on Task and add CREATE INDEX IF NOT EXISTS to db.py (same mechanism as PERF-006).
- **Behavior risk & rollback:** Semantics unchanged (same tasks selected/cancelled, same order). Keep tenant_id in every predicate (ADR-055). Rollback: revert helper + DROP index. Covered by auto-followup + task tests.
- **Suggested confirm-it measurement:** sqlite3 EXPLAIN QUERY PLAN SELECT * FROM task WHERE tenant_id=1 ORDER BY created_at DESC, id DESC before/after the index (confirm filesort gone). Spy TaskStore.list_filtered call count across a PUT /api/leads status→contacted.
- **⚠️ Rail / dependency flag:** Additive-migration schema rail (CLAUDE.md §8). No new dependency.
- **Merged from:** none (be-compute-auth #32).
- **Why this rank:** On the daily outreach write path; medium certainty + small magnitude today keep it here.

---

### PERF-024 — Eliminate the redundant in-route Pydantic validation pass on the list endpoints (candidates/my-leads/tasks)

**Rank 24**  ·  backend/app/main.py (candidates/my-leads/tasks serialization)  ·  _compute_  ·  certainty 🟡 medium  ·  effort ⚡ quick-win

- **Location:** backend/app/main.py:336-356 (candidates/my-leads build [OwnerSummary(**r)...]), :586-613 (tasks [_task_to_out...]), :985-1001 (_to_detail); owners_index_service.py:163,190 ({**owner,'status':status} spread)
- **What & why:** The list routes explicitly construct Pydantic instances (OwnerSummary(**r) per row, _task_to_out per task) then return them inside a response wrapper whose response_model causes FastAPI to validate/serialize the same payload a SECOND time. The data is our own trusted index/ORM, so the first validation is redundant — re-validating ~20 fields per row that FastAPI re-validates on the way out. The {**owner,'status':status} spread also rebuilds a ~24-key dict per row (carrying the holdings reference OwnerSummary then drops).
- **Grounded impact (real N):** my-leads default limit 2000 (main.py:353), candidates up to 2000 — up to 2000 OwnerSummary validations in-route + 2000 more in response_model per request.
- **Expected gain:** Halves per-row Pydantic work (one validation pass instead of two) — up to ~2000 fewer model validations per my-leads call.
- **Execution (paste-back work order):** Build in-route models with OwnerSummary.model_construct(**r) / TaskOut.model_construct(...) to skip the first validation (data trusted), letting response_model do the single authoritative pass (keeps OpenAPI schema + the one validation). Alternatively return plain dicts and let response_model validate once. Avoid response_model=None. Drop the holdings key before the spread in list_candidates/list_my_leads.
- **Behavior risk & rollback:** model_construct skips validation, so only on known-valid data; a malformed index field passes through until response_model catches it. Rollback: revert to OwnerSummary(**r). Response shape identical.
- **Suggested confirm-it measurement:** estimate-only locally (dev rows tiny); or microbench [OwnerSummary(**r) for r in rows] vs model_construct over 2000 dicts built from the real index.
- **⚠️ Rail / dependency flag:** OWNERS_INDEX_SCHEMA_VERSION — model_construct bypasses default-fill, so keep response_model (applies defaults) as the final pass.
- **Merged from:** none (backend-read #24).
- **Why this rank:** Backend read on worklist endpoints; medium certainty + modest per-row magnitude.

---

### PERF-025 — Cache the per-request auth DB resolution (tenant-by-name + user-by-email) keyed on the credentials-file signature

**Rank 25**  ·  backend/app/auth_service.py (resolve_principal/_principal_for) + auth.py  ·  _compute_  ·  certainty 🟡 medium  ·  effort 🔧 small

- **Location:** backend/app/auth_service.py:73-100 (resolve_principal → _principal_for), :111-133 (get_user_by_email/provision_user); backend/app/auth.py:84-105 (current_principal)
- **What & why:** Every authenticated request runs current_principal → resolve_principal → _principal_for, issuing ≥2 DB queries purely for authorization: TenantService.get_by_name(team) and AuthService.get_user_by_email(email). Correct per ADR-062/063, but the (username,team)→(tenant_id,user_id) mapping only changes when the credentials file changes (observable via mtime signature) — yet it is recomputed from scratch on every request, including high-frequency counts/candidates polls. (Confirmed: PBKDF2 is NOT on this path — it runs only in login()/change_password().)
- **Grounded impact (real N):** 2 indexed point-lookups on EVERY data request. On SQLite-in-process these are microseconds; on Postgres (prod via DATABASE_URL) they are ~2 network round-trips per request on every endpoint, multiplied by counts polling after each mutation. Structural per-request overhead on the entire authenticated surface.
- **Expected gain:** Removes 2 DB round-trips from the steady-state request path (cache hit) while preserving per-request file re-authorization. On Postgres ~2 fewer round-trips per request. Honest framing: latency-floor/cleanliness win, not a throughput rescue at a 2-person scale.
- **Execution (paste-back work order):** Keep the mtime-cached CredentialsFile check (file authority — unchanged). Add a per-process memo in resolve_principal keyed on (normalized_username, file_signature): on a hit where the username is still present with the same team, return the cached Principal without the get_by_name/get_user_by_email queries. Invalidate when the file signature changes (re-teaming bumps mtime via temp+rename). Still raise NotAuthorized when the username is absent from the current file. Guard so first-provision / team-change hits provision_user.
- **Behavior risk & rollback:** Must NOT weaken per-request file authority: the file presence + team check stays on every request; only the DB id resolution is memoized, invalidated by the signature. Risk: a cache outliving a team change — keying on file_signature prevents it. Rollback: delete the memo.
- **Suggested confirm-it measurement:** estimate-only on SQLite; to confirm the Postgres win, count queries per request with SQLAlchemy echo before/after (expect 2 fewer on cache hit).
- **⚠️ Rail / dependency flag:** ADR-062/063 — preserves the per-request file check; only caches the DB lookup, invalidated by the file signature.
- **Merged from:** backend-read #25 + be-compute-auth #31 (identical per-request auth-resolution caching).
- **Why this rank:** Every authenticated request, but tiny absolute cost at 2-person scale + medium certainty — structural-cleanliness win.

---

### PERF-026 — Quantify and bound the 42.8 MB owners index resident in every worker process (parsed object bloat)

**Rank 26**  ·  backend/app/owners_index_service.py (reload) + main.py module-load singleton  ·  _compute_  ·  certainty 🟡 medium  ·  effort 🔧 small

- **Location:** backend/app/owners_index_service.py:34-50 (reload: read_text + json.loads + sort); backend/app/main.py:116-117 (load once at import)
- **What & why:** reload() does json.loads(self.index_path.read_text()) — a transient ~42.8MB decoded string, then 16,237 nested Python dicts (~24 keys, nested holdings/structures/carriers). The resident structure is several times the 42.8MB on-disk size due to per-object overhead. Loaded at module import, so each uvicorn/gunicorn worker holds its own full copy — no shared-memory/mmap.
- **Grounded impact (real N):** 16,237 owners + 22,654 holdings parsed to native objects — Python representations of such JSON run ~3-6x file size, i.e. ~150-250MB RSS per worker for the index alone, replicated per worker. On the constrained Fly host this is the single largest steady-state memory consumer and caps worker count.
- **Expected gain:** read_bytes → json.loads(bytes) skips the str decode + frees the transient copy sooner (one ~43MB allocation avoided). The larger win is bounding resident set so worker count can scale — measured via RSS.
- **Execution (paste-back work order):** Cheap: json.loads(self.index_path.read_text()) → json.loads(self.index_path.read_bytes()). (orjson is faster but is a NEW DEPENDENCY — flag, do not add silently.) To bound RSS: drop fields the backend never serves from the in-memory dicts at load (the index carries owner_name_norm + full holdings; OwnerSummary serves neither for list endpoints — only lead_view needs holdings), or store heavy holdings out-of-line keyed by cluster id and load lazily in lead_view. Measure RSS first.
- **Behavior risk & rollback:** Low for read_bytes. The field-pruning/lazy-holdings variant must keep lead_view's holdings intact and tolerate stale/missing fields (schema-versioned rail). Rollback: revert to read_text / keep full dicts.
- **Suggested confirm-it measurement:** With .venv: measure RSS (resource.getrusage / tracemalloc) after OwnersIndexService init over the real owners_index.json; compare full-dict vs pruned-dict load.
- **⚠️ Rail / dependency flag:** ADR-051 — backend load-time only, does not redesign the ETL; orjson would be a NEW DEPENDENCY (flagged, optional).
- **Merged from:** none (backend-read #26).
- **Why this rank:** Memory/scaling rather than latency; medium certainty — bounds worker fan-out on the constrained host but no triage-felt latency.

---

### PERF-027 — facets step re-materializes the whole state's attribute table in memory for a global sort (a second memory peak after chunked compose)

**Rank 27**  ·  preprocess (--app-assets facets)  ·  _compute_  ·  certainty 🟡 medium  ·  effort 🔧 small

- **Location:** scripts/preprocess/facets.py:129-145 (_read_parcels_table, pa.concat_tables) + 167-172 (sort_by then write)
- **What & why:** _read_parcels_table streams each shard but then pa.concat_tables(tables) unions ALL shards into one in-memory Arrow table, and build_facets immediately table.sort_by([(interestingness_score, descending)]) over the whole thing. The 'bounded memory per shard' claim is defeated by the concat + global sort — the facets step holds the entire state's attribute set (minus geometry) in RAM at once, a second memory wall after the chunked compose. For FL ~11M rows × ~25 attribute columns (incl. JSON-string columns).
- **Grounded impact (real N):** FL ~11M parcels materialized + globally sorted in one Arrow table during --app-assets — the same 'load everything then operate' pattern ADR-051 chunked compose avoids, one stage downstream. Produces parcels_attr.parquet (the owners_index input lineage), so it runs on every full build.
- **Expected gain:** Bounded peak RSS at the facets stage (one shard + a merge buffer instead of the full state). The global sort is the only thing forcing full materialization.
- **Execution (paste-back work order):** (a) compute facets (value_counts/min_max) by accumulating per-shard with pyarrow.compute, deciding whether a global sort is needed afterward; (b) replace concat+sort with a pyarrow.dataset scan + ordered write_dataset, OR drop the global interestingness_score sort if DuckDB-WASM range queries don't require globally-sorted row groups (verify owners-filter-index.ts / the DuckDB read path first). If the sort IS required for row-group pruning, sort per-shard + k-way merge instead of full concat.
- **Behavior risk & rollback:** parcels_attr.parquet row CONTENT unchanged; only row ORDER / row-group layout may change if the sort is relaxed — verify the client's DuckDB queries don't depend on order. Self-contained to facets.py; one-file revert. Do NOT touch compose's chunked posture.
- **Suggested confirm-it measurement:** time `python scripts/preprocess.py --app-assets --state 30` and watch RSS; confirm facets.json + parcels_attr.parquet row counts/values match baseline.
- **⚠️ Rail / dependency flag:** Adjacent to ADR-051 but this is the facets stage, not chunked compose — fixing facets only. No new dep (pyarrow already used).
- **Merged from:** none (preprocess #41).
- **Why this rank:** Memory peak on a per-build dev stage; medium certainty + batch lane.

---

### PERF-028 — Reuse the precomputed geometry_valid column instead of recomputing GEOS is_valid in every sjoin pass

**Rank 28**  ·  preprocess (compose infra sjoin + parcel distress annotator)  ·  _compute_  ·  certainty 🟡 medium  ·  effort 🔧 small

- **Location:** scripts/preprocess/compose.py:155 (right[right.geometry.notna() & right.geometry.is_valid]); scripts/preprocess/annotators/spatial_attribute.py:85-86; produced at normalizers/state_parcels.py:445
- **What & why:** The normalizer already stores geometry_valid = geometry.notna() & geometry.is_valid on every parcel (state_parcels.py:445). Yet the infra→parcel sjoin (compose.py:155) and the parcel distress annotator (spatial_attribute.py:86) both RECOMPUTE geometry.notna() & geometry.is_valid on every parcel, every pass. GEOS is_valid is one of the most expensive geometry predicates, recomputed 2-3x in the infra pre-pass + once per chunk in the distress sjoin — redundant with a column already on disk.
- **Grounded impact (real N):** is_valid evaluated over full parcel geometry per pass: FL ~11M polygons × (2 infra passes + 1 distress pass) ≈ ~33M redundant GEOS validity checks for FL alone. Compounds PERF-016.
- **Expected gain:** Eliminates repeated is_valid computation on parcels (replace with a boolean column read); tens of millions of GEOS calls avoided per FL build. Stacks with PERF-016.
- **Execution (paste-back work order):** Where the shard/target carries geometry_valid, filter with chunk[chunk['geometry_valid']] / geo[geo['geometry_valid']] instead of .geometry.notna() & .geometry.is_valid. Guard fallback to recompute when the column is absent (e.g. towers, which lack it). In spatial_attribute.annotate gate on filter_invalid_target_geom and 'geometry_valid' in target.columns.
- **Behavior risk & rollback:** geometry_valid is defined identically and geometry isn't mutated between normalize and these sjoins, so results match. Theoretical staleness if a future step edits geometry without refreshing the flag — keep the recompute fallback. Per-file revert.
- **Suggested confirm-it measurement:** `python scripts/preprocess.py --state 30`; assert the set of parcels with in_oz/in_qct/distress_overlays and the infra→parcel matches are unchanged.
- **⚠️ Rail / dependency flag:** Shared tower+parcel annotator — keep the tower path (no geometry_valid col) on the recompute fallback; preserves EPSG:4326 rail.
- **Merged from:** none (preprocess #40).
- **Why this rank:** Stacks with PERF-016 for large GEOS savings; medium certainty (staleness fallback) + batch lane.

---

### PERF-029 — Distress annotator does 3 separate per-row index.map passes per chunk to derive 3 columns from one hit-set

**Rank 29**  ·  preprocess (spatial-attribute annotator, parcel distress)  ·  _compute_  ·  certainty 🟡 medium  ·  effort 🔧 small

- **Location:** scripts/preprocess/annotators/spatial_attribute.py:88-104
- **What & why:** After the sjoin builds per_target (parcel_idx → set of overlay categories), annotate() loops over derived_columns doing out[col] = out.index.map(lambda i: fn(per_target.get(int(i), set()))) once PER derived column. For the distress spec there are 3 columns (distress_overlays, in_oz, in_qct), so it walks the full parcel index 3 times with a Python lambda + int() cast + dict.get per row, recomputing per_target.get(i) three times. Plus out = target.copy() is a full chunk copy.
- **Grounded impact (real N):** Runs in the main chunk loop on every parcel of every state (FL ~11M, AR ~2.1M). ~3 × 11M = ~33M Python lambda/dict-get calls per FL build for distress column derivation, on top of the redundant is_valid (PERF-028).
- **Expected gain:** Fold the 3 derivations into a single pass over per_target (one row→set resolution, then build all derived columns), eliminating 2 of 3 full-index Python walks (~-66% of this step's Python overhead).
- **Execution (paste-back work order):** Compute the per-row set once: sets = [per_target.get(i, EMPTY) for i in out.index], then derive each column from that single list (out['distress_overlays'] = [sorted(s) for s in sets], out['in_oz'] = ['opportunity_zone' in s for s in sets], etc.). Keeps the SpatialAttributeSpec.derived_columns contract.
- **Behavior risk & rollback:** Pure refactor of how derived columns are filled; values identical. Shared annotator (tower + parcel) — test both. Per-file revert.
- **Suggested confirm-it measurement:** `python scripts/preprocess.py --state 30`; diff in_oz/in_qct/distress_overlays columns of MT parcels for equality.
- **⚠️ Rail / dependency flag:** Shared tower+parcel annotator — keep one body, do not fork per surface.
- **Merged from:** none (preprocess #42).
- **Why this rank:** Stacks with PERF-028 on the same annotator; medium certainty + batch lane.

---

### PERF-030 — Dead parcel-filter code path retained in the main bundle (orphaned FilterEngine/url + retained DuckDB parcel-query methods)

**Rank 30**  ·  fe-compute / bundle (delivery-adjacent)  ·  _perceived_  ·  certainty 🟡 medium  ·  effort 🔧 small

- **Location:** app/src/lib/filter-engine.ts (whole file, never imported); app/src/lib/url.ts (never imported); app/src/lib/query.ts:36-65 (countQuery/idQuery/ownerSearchQuery/parcelRowQuery); app/src/lib/duckdb.ts:97-162 (loadState/count/matchingIds/searchOwners/fetchParcel — only loadTowerPoints at 174 is live); app/src/lib/filters.ts (FilterState half)
- **What & why:** The pre-redesign parcel-fade path is dead: FilterEngine and url.ts are imported by nothing, and DuckDbEngine's loadState/count/matchingIds/searchOwners/fetchParcel have no callers (grep-verified) — only loadTowerPoints is live. Orphaned modules tree-shake away, but the DuckDbEngine query METHODS will NOT: duckDb is instantiated and attached to window.__duckDb (duckdb.ts:212-214), so class methods + their query.ts/filters.ts deps are retained in the 1.4MB single chunk. The app never reads parcels_attr.parquet anymore, yet the SQL builders targeting it ship to every user.
- **Grounded impact (real N):** Dead parcel-query method bodies + query.ts builders + the FilterState half of filters.ts are bytes delivered on the co-founder's first load that can never execute (several KB of JS; exact via build diff). Confirms the parcels_attr full-scan hunt is moot.
- **Expected gain:** Removing the dead methods + their deps and deleting filter-engine.ts/url.ts shrinks the main chunk (several KB) and removes a class of confusing dead code from the hot module.
- **Execution (paste-back work order):** Confirm zero runtime callers (grep shows none), then: delete filter-engine.ts + url.ts; remove loadState/count/matchingIds/searchOwners/fetchParcel + unused query imports from duckdb.ts keeping only loadTowerPoints; prune the unused exports in query.ts (countQuery/idQuery/ownerSearchQuery/parcelRowQuery, composeWhere) and the parcel-only FilterState/FILTER_SPECS in filters.ts. Run the unit suite — some tests may reference these. Do NOT remove the DuckDB-WASM dep (loadTowerPoints needs it).
- **Behavior risk & rollback:** Only the dead path; live tower load untouched. Risk: a test or window.__duckDb E2E hook references a removed method — search tests/ first. Rollback: git revert. No data/schema/tenant changes.
- **Suggested confirm-it measurement:** vite build before/after, then du/report the index-*.js chunk size delta in app/dist/assets. Run npm run test to catch test references.
- **⚠️ Rail / dependency flag:** Keep loadTowerPoints + the DuckDB-WASM dep (live tower read path). No new dependency; only removes code.
- **Merged from:** none (fe-compute #7).
- **Why this rank:** Bundle cleanup + dead-code removal; medium certainty, modest KB magnitude.

---

### PERF-031 — Stop the 5-second QTimer from re-walking the entire 55 GB raw tree on the UI thread

**Rank 31**  ·  pullers (desktop / app_puller)  ·  _compute_  ·  certainty 🟢 high  ·  effort ⚡ quick-win

- **Location:** app_puller/main_window.py:141-143 (QTimer → _refresh_header) + :622-629 (_refresh_header) → scripts/fetch/storage.py:95-106 (directory_bytes)
- **What & why:** On construction the puller starts a 5s QTimer wired to _refresh_header, which calls directory_bytes(RAW_ROOT) — rglob('*') + p.stat() over EVERY file under data/raw — purely to render the 'Total raw data: X' label. This runs every 5 seconds for the window's lifetime, idle or not, on the Qt main thread. Per-source byte totals are already cached in the manifest (entry.bytes), so the recursive walk recomputes data the manifest holds.
- **Grounded impact (real N):** Measured: data/raw is 55 GB across 1,498 files. That is ~1,498 stat() syscalls every 5s ≈ ~18,000 stat/min, forever, on the UI thread. Warm-cache ~17-34 ms/pass today, but scales with file count and explodes on cold page cache, spinning/external disk, or a network-mounted data dir — exactly the long-running-puller scenario where it causes visible stutter.
- **Expected gain:** Eliminates ~18,000 stat/min of UI-thread I/O; header refresh drops from O(1,498 files) to ~25 dict lookups (~17-34 ms → <1 ms warm; far larger on slow disk).
- **Execution (paste-back work order):** In _refresh_header replace total = directory_bytes(RAW_ROOT) with total = sum(self._manifest.entry(s.id).bytes for s in self._sources). Keep the real directory_bytes walk ONLY on disk-changing events (_on_fetch_all_done, _rescan_disk, _detect_manual_installs, which already update entry.bytes). Optionally slow or remove the 5s timer (totals only change on fetch/rescan). Keep manifest as the single writer.
- **Behavior risk & rollback:** One label's number. Cached sum omits in-flight .partial/.old bytes the walk includes — arguably more correct; if exact footprint is desired, recompute once in _on_fetch_all_done. Rollback: restore the single line.
- **Suggested confirm-it measurement:** Already measured (~20 ms warm). Confirm the steady-state win with fs_usage -f filesys -p <pid> | grep stat for 15s before/after, or confirm the timer no longer touches disk.
- **⚠️ Rail / dependency flag:** none — no Qt added to scripts/fetch; manifest stays the single writer; atomic-write invariants preserved.
- **Merged from:** none (pullers #46).
- **Why this rank:** High certainty, real UI-thread jank — but pullers are LOW weight (rarely-run dev tool, not the co-founder's daily triage), which caps the rank.

---

### PERF-032 — Use cached manifest bytes in _refresh_row instead of re-statting each source's current/ per refresh

**Rank 32**  ·  pullers (desktop / app_puller)  ·  _compute_  ·  certainty 🟢 high  ·  effort ⚡ quick-win

- **Location:** app_puller/main_window.py:595 (_refresh_row) called from :616-620 (_refresh_all_rows) → scripts/fetch/storage.py:95-106 (directory_bytes)
- **What & why:** _refresh_all_rows loops every source and calls _refresh_row, which runs directory_bytes(current_dir(source.id)) — a full recursive rglob+stat of that source's current/ — once per row, every time the table is redrawn (after each fetch, after rescan, on selection changes). The manifest already caches entry.bytes, so each row redraw re-walks disk for a number already in memory.
- **Grounded impact (real N):** _refresh_all_rows fires N source-walks per redraw. With FL fdor_nal (67 per-county shapefiles) and NC nc_onemap_parcels (~490-1,186 page files) in the set, a single full refresh re-stats well over a thousand files — invoked on every fetch completion and rescan. Combined with PERF-031, one refresh can touch the whole 1,498-file / 55 GB tree twice.
- **Expected gain:** Per-row disk walk → O(1) manifest read. Eliminates the per-refresh re-stat of every source's current/ (hundreds-to-thousands of stat calls per redraw).
- **Execution (paste-back work order):** In _refresh_row (line 595) replace size_bytes = directory_bytes(current_dir(source.id)) with size_bytes = entry.bytes (entry already fetched on line 588). The manifest is kept current by _detect_manual_installs, mark_fetch_ok, mark_manual_install, so the cached value is authoritative. _detect_manual_installs runs before the refresh (:114 before :135).
- **Behavior risk & rollback:** The per-row SIZE column. If files change on disk out-of-band without a rescan, the column shows last-known size until the next rescan — consistent with how local_version already works. Rollback: restore the one line.
- **Suggested confirm-it measurement:** estimate-only (same mechanism as PERF-031, already timed). Optionally add a counter in directory_bytes and confirm call count per _refresh_all_rows drops from N to 0.
- **⚠️ Rail / dependency flag:** none — manifest single-writer + atomic-write invariants preserved.
- **Merged from:** none (pullers #47).
- **Why this rank:** High certainty quick-win; LOW pullers lane weight keeps it adjacent to PERF-031.

---

### PERF-033 — Replace full byte-sum existence test in _detect_manual_installs with a cheap any() probe and de-duplicate the triple walk

**Rank 33**  ·  pullers (desktop / app_puller)  ·  _compute_  ·  certainty 🟡 medium  ·  effort 🔧 small

- **Location:** app_puller/main_window.py:157-211 (_detect_manual_installs), specifically :168 (has_files), :170-178 and :193-201 (rglob + directory_bytes)
- **What & why:** For every source on startup/rescan, has_files = directory_bytes(cur) > 0 computes the FULL recursive byte total of current/ just to answer 'is there at least one file'. Then the newly-detected-install branch walks the same directory AGAIN with cur.rglob('*') to build the file list and a THIRD time with directory_bytes(cur) to set entry.bytes — up to three recursive walks per source. Summing every file under a 55 GB tree to test '> 0' is pure waste.
- **Grounded impact (real N):** Runs across all ~25 sources on every startup (main_window.py:114) and every Rescan disk click (:929). The has_files byte-sum alone re-walks the whole 55 GB / 1,498-file tree once per rescan even when nothing changed; the install branch adds 2 more walks (for NC, ~490-1,186 files walked 3×).
- **Expected gain:** Existence check O(all files) → O(1) (first dir entry). Install branch 3 walks → 1. Removes a whole-tree re-walk per rescan.
- **Execution (paste-back work order):** 1) Replace has_files = directory_bytes(cur) > 0 (line 168) with has_files = cur.exists() and any(p.is_file() for p in cur.rglob('*')) (stops at first file). 2) In the install branches (:170-178, :193-201) walk once into paths = [p for p in cur.rglob('*') if p.is_file() and not p.is_symlink()], then set entry.files + entry.bytes from that single list instead of calling directory_bytes(cur) again. Keep manifest single-writer + atomic-save.
- **Behavior risk & rollback:** Startup/rescan detection only; output (entry.files/bytes) byte-identical. Rollback: revert the three edits. Lives in app_puller (Qt) — fine.
- **Suggested confirm-it measurement:** estimate-only, or time _detect_manual_installs() before/after via a temporary perf_counter log around main_window.py:114 with the real 55 GB tree.
- **⚠️ Rail / dependency flag:** none — no Qt added to scripts/fetch; manifest single-writer preserved.
- **Merged from:** none (pullers #48).
- **Why this rank:** Medium certainty, real triple-walk waste; LOW pullers lane caps it.

---

### PERF-034 — ScoringPreset default-toggle re-queries all presets instead of one UPDATE

**Rank 34**  ·  backend/app/scoring_preset_store.py  ·  _compute_  ·  certainty 🟡 medium  ·  effort ⚡ quick-win

- **Location:** backend/app/scoring_preset_store.py:63 (_clear_other_defaults calls self.list()), used by :33 (create) and :45 (set_default)
- **What & why:** _clear_other_defaults() calls self.list() (full SELECT of the tenant's presets) and loops in Python flipping is_default=False, when the same effect is one UPDATE scoring_preset SET is_default=0 WHERE tenant_id=? AND id<>? AND is_default=1. create(is_default=True) additionally flush()es then runs this clear; set_default() does get() then the clear. Extra round-trip + full hydration on a write that touches at most one other row.
- **Grounded impact (real N):** Presets per tenant are few, so absolute cost is small — tidiness/round-trip finding, not a hot path. Fires only on preset create-as-default and set-default (rare admin actions).
- **Expected gain:** Replaces SELECT-all + per-row ORM mutation with one targeted UPDATE on set-default/create-default. -1 query + no row hydration.
- **Execution (paste-back work order):** Replace _clear_other_defaults(keep_id) with session.execute(update(ScoringPreset).where(ScoringPreset.tenant_id==self.tenant_id, ScoringPreset.id!=keep_id, ScoringPreset.is_default.is_(True)).values(is_default=False)). Keep the keep_id row's is_default set by the caller. Preserve commit boundaries.
- **Behavior risk & rollback:** Same end state (one default per tenant). Keep tenant_id in the predicate (ADR-055). Watch ORM identity-map staleness after a bulk UPDATE — expire_all() or re-fetch; the existing refresh() in set_default covers the kept row. Rollback: restore the loop.
- **Suggested confirm-it measurement:** unit: spy session query count across set_default() before/after (expect 1 fewer SELECT); assert one default remains.
- **Merged from:** none (be-compute-auth #35).
- **Why this rank:** Rare admin action, tiny magnitude; medium certainty quick-win — lowest of the main-tier backend items.

---

## Appendix A — Speculative (low confidence)

Worth-a-look items kept out of the main report so the signal stays clean. Lower certainty and/or magnitude; two are explicitly *recommend-no-change* (PERF-041/042) and one is a correctness/robustness fix, not a perf gain (PERF-040).

### PERF-035 — Owner + ASR search scans all 16,237 owners and 80,814 features per query

**Rank 35**  ·  fe-compute / search  ·  _compute_  ·  certainty ⚪ low  ·  effort ⚡ quick-win

- **Location:** app/src/lib/filter-model.svelte.ts:116-123 (searchOwners filter+sort over all owners); app/src/components/FilterPanel.svelte:61-79 (runSearch also filters all towerPoints features for ASR hits); app/src/components/LeadPage.svelte:41 (searchOwners for merge picker)
- **What & why:** searchOwners does owners.filter(substring).sort(score).slice(limit) over the full 16,237-owner array, and runSearch additionally does app.towerPoints.features.filter(asr.includes).slice(5) over all 80,814 features, per query. The FilterPanel path is debounced (180ms, min 2 chars) so it's not a per-keystroke storm, but each settled query is still a full linear scan of both large collections; LeadPage's merge picker calls searchOwners directly.
- **Grounded impact (real N):** Every settled search: a 16,237-owner substring scan + (FilterPanel) an 80,814-feature substring scan. Acceptable today due to the 180ms debounce; degrades as the index grows beyond 4 anchor states.
- **Expected gain:** A prebuilt lowercased index / early-exit avoids re-lowercasing 16,237 names per query; ASR search could short-circuit after 5 hits instead of filtering all 80,814 (small).
- **Execution (paste-back work order):** In searchOwners precompute a lowercased owner_name once (at load in owners-filter-index.ts toRecord, or a one-time derived array) instead of .toLowerCase() per row per query. For ASR search in runSearch, break out after collecting 5 hits rather than .filter().slice(5) over all 80,814. Keep the 180ms debounce.
- **Behavior risk & rollback:** Owner/ASR autocomplete — keep ordering identical (score desc / first-N). Rollback trivial. No data changes.
- **Suggested confirm-it measurement:** Micro-benchmark searchOwners('a') over the loaded 16,237-owner index in the console (performance.now around 100 calls). Estimate-only otherwise.
- **Merged from:** none (fe-compute #6).
- **Why this rank:** Already debounced, so low live impact + low certainty — speculative.

---

### PERF-036 — maplibre-gl.css (72KB of the 116KB sheet) is in the render-blocking boot stylesheet even on the Dashboard landing

**Rank 36**  ·  app/ frontend — critical CSS  ·  _perceived_  ·  certainty ⚪ low  ·  effort ⚡ quick-win

- **Location:** app/src/main.ts:2 (import 'maplibre-gl/dist/maplibre-gl.css'); bundled into app/dist/assets/index-*.css (119,631 bytes raw / 18KB gzip); maplibre-gl.css alone is 72KB
- **What & why:** main.ts imports the full 72KB maplibre-gl.css into the single render-blocking stylesheet, so it loads and blocks first paint even when the user lands on the Dashboard (no map visible). gzip keeps the wire cost low (whole sheet 18KB), so the impact is small — but it's still render-blocking CSS for controls the landing never shows.
- **Grounded impact (real N):** 119,631-byte combined CSS (18KB gzip) is render-blocking on first paint; ~72KB is MapLibre control styling not needed until the map is shown.
- **Expected gain:** (estimate) Small — shrinks the critical CSS blocking first paint when MapLibre CSS moves with the deferred map chunk; mostly a parse/blocking win, minimal wire win given gzip.
- **Execution (paste-back work order):** Move import 'maplibre-gl/dist/maplibre-gl.css' out of main.ts into MapView.svelte (or the lazy map chunk) so it loads with the map. Combine with PERF-001 and PERF-004 so the MapLibre CSS lands in the map's chunk.
- **Behavior risk & rollback:** If the map renders before its CSS loads, controls could flash unstyled briefly — acceptable since the map is deferred. Rollback: move the import back to main.ts.
- **Suggested confirm-it measurement:** vite build + check the critical index CSS size; chrome-devtools coverage panel on the Dashboard landing to see unused MapLibre CSS rules.
- **Merged from:** none (fe-perceived #18).
- **Why this rank:** Low certainty, small magnitude (gzip already small) — speculative.

---

### PERF-037 — owners_index does a second full groupby + to_dict('records') + four separate .map passes to attach holdings detail

**Rank 37**  ·  preprocess (owners-index build)  ·  _compute_  ·  certainty ⚪ low  ·  effort ⚡ quick-win

- **Location:** scripts/preprocess/owners_index.py:351-358 (resolve) + 361-378 (_build_detail)
- **What & why:** resolve() already groups df by _cluster once (line 307) for the aggregate. _build_detail then groups the SAME df by _cluster AGAIN (line 366) and calls group.to_dict('records') per cluster, parsing infrastructure_summary JSON per parcel. Then resolve attaches the result with FOUR separate out['col'] = out['display_cluster_id'].map(lambda c: detail[c][i]) passes — four full walks of the index to unpack one tuple. The double groupby + 4x map are avoidable.
- **Grounded impact (real N):** Runs over the structure-bearing parcels nationally (the Lead universe — a few thousand today, O(parcels_with_infra) growing as coverage expands). Small at current N but structural repeated work (two groupbys + record-dict materialization + 4 index walks) in the build that produces the 41MB in-memory backend index.
- **Expected gain:** One groupby instead of two; one assignment of a 4-tuple instead of 4 index.map passes. Modest wall-clock today, cleaner as N grows.
- **Execution (paste-back work order):** Compute detail in the SAME groupby used for the aggregate (or build detail once and assign via out[['holdings','mailing_address','tallest_tower_height_m','active_tower_count']] = out['display_cluster_id'].map(detail).apply(pd.Series)) instead of four lambda maps. Avoid group.to_dict('records') by iterating only the needed columns.
- **Behavior risk & rollback:** owners_index.json content must be identical (schema v5 safe-defaults rail). Verify holdings/mailing/tallest/active fields byte-match. Single-file revert.
- **Suggested confirm-it measurement:** run write_owners_index against the existing composite and diff owners_index.json vs baseline (estimate-only on timing at current N).
- **⚠️ Rail / dependency flag:** OWNERS_INDEX_SCHEMA_VERSION=5 — keep field shapes unchanged; do not bake overrides into parquet (resolution stays in OwnersIndexService.effective).
- **Merged from:** none (preprocess #44).
- **Why this rank:** Low certainty, small magnitude at current N; batch lane — speculative.

---

### PERF-038 — io._prep_complex_cols full-frame copy + per-cell json.dumps on every shard write

**Rank 38**  ·  preprocess (io parquet writer)  ·  _compute_  ·  certainty ⚪ low  ·  effort 🔧 small

- **Location:** scripts/preprocess/io.py:30-69 (_prep_complex_cols, called by write_geoparquet/write_parquet)
- **What & why:** Every shard write calls _prep_complex_cols, which does a full df.copy() then, for each object column whose head(50) sample contains a dict/list, runs df[col].map(_encode) (per-cell isinstance + json.dumps) over the entire column. For parcels there are several such columns (infrastructure_summary, interestingness_components, _raw, distress_overlays, extras, geom_bbox), so each shard write does a full copy plus multiple full-column json.dumps passes.
- **Grounded impact (real N):** Called once per shard write in the chunk loop (FL ~67 shards) over ~11M parcels per state; the full df.copy() duplicates each chunk in memory transiently and the per-cell json.dumps is carried in Python. On the hot write path of every compose build.
- **Expected gain:** Avoiding the unconditional full copy (copy only if a column needs re-encoding) and narrowing the scan to known-complex columns removes one full chunk duplication per shard + the head(50) sniff over non-complex object columns (serialization itself stays).
- **Execution (paste-back work order):** Skip df = df.copy() when no object column needs encoding (detect first, copy lazily). Optionally let callers pass known complex-column names to skip the head(50) heuristic. Leave the json.dumps (required for parquet of nested Python objects), or consider native Arrow list/struct types to skip JSON entirely — flag as a larger change.
- **Behavior risk & rollback:** On-disk bytes must stay identical (downstream readers json.loads these columns). Low-risk if you only change WHEN the copy happens. Single-file revert.
- **Suggested confirm-it measurement:** `python scripts/preprocess.py --state 30`; byte-compare a written shard parquet vs baseline; estimate-only on timing.
- **Merged from:** none (preprocess #43).
- **Why this rank:** Low certainty, serialization cost largely unavoidable; batch lane — speculative.

---

### PERF-039 — _apply_lookup attaches infra columns via a per-column Python index.map

**Rank 39**  ·  preprocess (compose, post-chunk infra enrichment)  ·  _compute_  ·  certainty ⚪ low  ·  effort ⚡ quick-win

- **Location:** scripts/preprocess/compose.py:176-188 (_apply_lookup)
- **What & why:** _apply_lookup adds parcel attributes back onto the infra tables with infra[col] = infra.index.map(lambda i, col=col: lookup.get(int(i), {}).get(col)) once per column — a Python dict-of-dicts walk per column (int() cast + nested .get per row). Cheap because infra (towers+solar) is small, but a quadratic-feeling pattern (rows × columns of Python gets) that would be a single DataFrame merge.
- **Grounded impact (real N):** Infra tables are small (FL towers 3.6MB, AR 1.3MB; row counts in the low thousands), so absolute cost is minor — flagged for completeness. Scales with tower/solar count, not parcels.
- **Expected gain:** Replacing per-column index.map with one pd.DataFrame.from_dict(lookup, orient='index') join is cleaner and ~Nx faster where N=#columns, but magnitude is small given thousands of infra rows.
- **Execution (paste-back work order):** Build add = pd.DataFrame.from_dict(lookup, orient='index') (index = infra row index), then infra = infra.join(add) in one shot. Preserve column set (union of keys) and missing→NaN behavior.
- **Behavior risk & rollback:** Identical columns/values (NaN where absent). Single-call-site revert.
- **Suggested confirm-it measurement:** estimate-only (infra tables tiny); optionally diff towers.parquet enriched columns vs baseline after --state 30.
- **Merged from:** none (preprocess #45).
- **Why this rank:** Low certainty, minor magnitude (small infra tables); batch lane — speculative.

---

### PERF-040 — Login throttle: bounded growth confirmed, but shared mutable state is unlocked under the sync threadpool

**Rank 40**  ·  be-compute-auth / login throttle  ·  _compute_  ·  certainty ⚪ low  ·  effort ⚡ quick-win

- **Location:** backend/app/login_throttle.py:45-101 (_failures dict / deque, _recent, _maybe_sweep); single shared instance backend/app/main.py:122 (_login_throttle)
- **What & why:** GROWTH is fine (_recent() prunes + deletes empty buckets; _maybe_sweep() drops expired keys every 256 failures — no leak). LOCKING is the gap: the one process-wide LoginThrottle is mutated from FastAPI's sync threadpool (the login route is plain def → anyio worker thread). _failures is a defaultdict[deque] mutated without a lock; under concurrent failed-login spray, _recent() can `del self._failures[key]` while another thread reads/appends. The GIL makes individual ops atomic-ish, but read-modify-delete sequences are not, so a rare KeyError/lost-update is possible. Latent correctness risk, not a throughput cost.
- **Grounded impact (real N):** Negligible performance impact (tiny, bounded structure). Concurrency exposure low for a 2-person team but nonzero on the public login endpoint (morphyconsulting.com) under credential-stuffing spray — exactly when the throttle matters.
- **Expected gain:** No measurable latency/throughput gain — robustness fix. Removes a rare-crash / lost-decrement risk on the login path under concurrent failures.
- **Execution (paste-back work order):** Wrap the mutating sections (record_failure, _recent's prune+delete, _maybe_sweep, reset) in a threading.Lock held only for the dict/deque ops (microsecond critical sections). Initialize self._lock = threading.Lock() in __init__. No API change. Alternatively document the GIL assumption — but given the public surface, a lock is cheap insurance.
- **Behavior risk & rollback:** Tiny critical sections; no observable behavior change. Rollback = remove the lock. Existing throttle tests (clock-injected) still pass.
- **Suggested confirm-it measurement:** estimate-only (race timing-dependent). Optionally stress with 50 parallel bad logins for one key and confirm no KeyError in logs; correctness, not timing.
- **⚠️ Rail / dependency flag:** Do not remove per-request authority / throttle behavior — only adds a lock, preserving sliding-window semantics. No new dependency (threading is stdlib).
- **Merged from:** none (be-compute-auth #34).
- **Why this rank:** Not a perf finding (correctness/robustness); low certainty — speculative appendix.

---

### PERF-041 — Avoid the redundant remote_version() probe at the start of every fetch() (low value — likely leave as-is)

**Rank 41**  ·  pullers (headless / scripts/fetch)  ·  _compute_  ·  certainty ⚪ low  ·  effort ⚡ quick-win

- **Location:** scripts/fetch/sources/fcc_uls.py:220, hud_oz.py:91, nc_onemap_parcels.py:166 (pattern: rv = self.remote_version() first line of fetch); orchestrated by scripts/fetch/puller.py:131-142
- **What & why:** check_one (puller.py:63-94) calls source.remote_version() and stores it. Moments later, when the same source is fetched, each fetch() re-calls self.remote_version() as its first line ('capture once; avoid 2nd HEAD post-download'). For HEAD-based sources that is one extra HEAD; for nc_onemap_parcels and hud_oz remote_version() is a real metadata GET, so a 'Check then Pull' sequence probes the publisher's metadata endpoint twice within seconds.
- **Grounded impact (real N):** One extra network round-trip per fetched source. Negligible against the payloads it precedes (fcc_uls l_micro ~185MB, a_lease_608 ~275MB; NC OneMap ~30-60 min). Real but tiny redundancy.
- **Expected gain:** Saves 1 HEAD/metadata-GET per fetched source per run (a handful per full sweep). Sub-second; effectively unmeasurable against multi-MB/GB downloads.
- **Execution (paste-back work order):** Optional and only if it stays correct: have fetch_one pass the already-known manifest.entry(sid).remote_version into fetch() as an optional arg; sources reuse it when present, falling back to remote_version() otherwise. Given the correctness rationale (the snapshot's version should reflect what was actually pulled), the safer call is to LEAVE AS-IS. Do not remove the post-download version capture.
- **Behavior risk & rollback:** Reusing the cached version risks recording a stale remote_version if upstream changed between check and fetch (a real correctness risk). Recommend NOT changing unless the tiny saving matters. Rollback trivial.
- **Suggested confirm-it measurement:** estimate-only.
- **⚠️ Rail / dependency flag:** none — no scraping added to MANUAL_ONLY; no Qt in scripts/fetch.
- **Merged from:** none (pullers #49).
- **Why this rank:** Lowest impact, low certainty, recommended no-change; LOW pullers lane — bottom of the appendix.

---

### PERF-042 — arcgis_query_all holds the whole layer in memory and serializes it as one giant JSON string (low value, national-only)

**Rank 42**  ·  pullers (headless / scripts/fetch)  ·  _compute_  ·  certainty ⚪ low  ·  effort 🔧 small

- **Location:** scripts/fetch/sources/_helpers.py:81-132 (arcgis_query_all); callers hud_oz.py:90-104, hud_qct.py, arc_distressed.py
- **What & why:** arcgis_query_all paginates an ArcGIS layer, reads each page fully into a string via fetch_text(url, max_bytes=200*1024*1024), json.loads it, appends every feature to one in-memory all_features list, then json.dumps the entire FeatureCollection into a single bytes object before writing. Peak memory ≈ full parsed feature list + one full page string+dict + the complete serialized output string simultaneously.
- **Grounded impact (real N):** Only used by national distress overlays — HUD OZ (~8,700 tracts, ~30MB GeoJSON), HUD QCT (~17,000 polygons), ARC. NOT anchor-state parcel paths, run rarely (HUD OZ cadence effectively static). Real but bounded to tens of MB on an infrequent batch op.
- **Expected gain:** Lower peak RSS during these three fetches (avoid holding parsed list + full output string at once); modest tens-of-MB reduction. No throughput change worth measuring.
- **Execution (paste-back work order):** If ever worth it: stream the output — open dest .partial, write {"type":"FeatureCollection","features":[, then write each page's features incrementally with comma separators as pages arrive (drop the page dict after writing), then close ]}; rename on success (atomic-write contract). Removes the all_features accumulation + the single big json.dumps. Keep the EPSG:4326 / FeatureCollection shape.
- **Behavior risk & rollback:** Streaming JSON-array assembly is fiddly (separator/encoding correctness); a bug yields malformed GeoJSON. Given low impact, prefer leaving as-is unless a memory issue is observed. Rollback: revert to list+dumps.
- **Suggested confirm-it measurement:** estimate-only, or /usr/bin/time -l python -c 'fetch hud_oz' for peak RSS before/after (requires the live ArcGIS endpoint; skipif in CI per the external-binary/network test posture).
- **⚠️ Rail / dependency flag:** none — preserves atomic-write + EPSG:4326 output shape; no new dependency.
- **Merged from:** none (pullers #50).
- **Why this rank:** Low impact (rare national-only batch), low certainty; LOW pullers lane — speculative.

---

## 5. Coverage & caveats

_"We looked everywhere" is not claimed where it isn't true._

Merged from the 6 lane coverage notes. NO live measurements were run by any finder or by this stage — every numeric gain is an estimate; each finding names the cheapest local confirmation. Grounded N is measured from disk, not invented: owners_filter.json = 10.89MB / 16,237 owners; 80,814 towers across anchor states (FL 53,010 / AR 15,789 / WV 7,330 / MT 4,685); owners_index.json = 41-42.8MB / 16,237 owners / 22,654 holdings; DuckDB eh.wasm 34MB raw (~7MB gzip); index.js 1.43MB (379KB gzip); solar GeoJSON ~2.74MB; favicon 98,887 bytes; data/raw 55GB / 1,498 files. KEY STRUCTURAL FACTS: (1) the DuckDB parcel-filter path (parcels_attr scans, composeWhere, count/matchingIds) is DEAD — the live app never reads parcels_attr.parquet; DuckDB-WASM is used only by loadTowerPoints over the small towers.parquet files (so the parcels_attr full-scan hunt resolved to dead code, PERF-030). (2) Backend dev DB is tiny (lead=5, contact_attempt=14, app_user=8, tenant=3, task=1) so N+1 / filesort costs are STRUCTURAL — reasoned at production scale, not observed; EXPLAIN QUERY PLAN was run on the live dev sqlite and confirmed the TEMP B-TREE filesorts and existing single-column indexes. (3) PBKDF2 (240k iters) confirmed OFF the per-request path (login/change_password only); the per-request users.txt check is a single mtime-cached stat(). (4) Cross-state owner clustering is O(n) hash-groupby (no O(n^2)); the normalizer's regex scalars are already per-distinct-value via _map_unique. NOT exhaustively read (could hide further waste): individual state_parcel_adapters/*.py; non-parcel normalizers (fcc_asr, fcc_uls, fcc_dat, hud_overlays, faa_oeaaa, eia_860/860m, arc_distressed, usda_persistent_poverty, hifld_towers, uspvdb, state_billboards); tiles.py, app_assets.py, catalog_builder.py, manifest.py, quality_report.py, county_boundaries.py; uls_to_asr.py beyond line 130 (the EPSG:5070 spatial fallback matcher); backend write routes beyond how they invoke reads; a deeper owners-index serialization pass. No live Lighthouse / vite build / chrome-devtools trace / preprocess build was executed (report-only). Per the rails, deliberately EXCLUDED as accepted posture (not findings): the unauthenticated :8765 static map-data server; per-request users.txt re-authorization (its cost characterized in PERF-025 but authority not removed); the ADR-051 chunked-compose memory posture (PERF-015/016/027/028 are cheap wins / the separate facets stage, not a compose redesign); the puller's intentional sequential fetch. One finding (PERF-019, Caddy immutable cache + brotli) is a production-config work order flagged report-only / do-not-deploy.

**Dedup ledger (50 → 42):** 50 raw findings → 42 ranked, via 8 same-root-cause merges (strongest framing kept; merged_from records each): (1) PERF-002 = fe-compute #1 (filter debounce) + fe-perceived #15 (matchingClusterIds full 16k owner scan) — same un-debounced filter recompute; primary fix is the debounce. (2) PERF-010 = fe-compute #4 + fe-perceived #14 (filterTowers full 80,814-feature rebuild + MapLibre re-cluster on every filter change) — same setData no-op-guard fix. (3) PERF-011 = fe-compute #5 + fe-perceived #11 (identical 80,814 main-thread SHA-1 hashes at boot in rowsToFeatureCollection). (4) PERF-005 = backend-read #19 (counts scans 16k owners) + be-compute-auth #33 (three independent full 16k passes per nav) — same counts/worklist redundant-scan root cause. (5) PERF-009 = backend-read #20 (memoize effective() + single-owner fast path) + be-compute-auth #29 (per-row owner_name_of rebuilds the full merged index) — same effective() memoization. (6) PERF-006 = backend-read #21 + be-compute-auth #30 (identical contact_attempt composite-index fix). (7) PERF-008 = backend-read #23 (/api/activity double scan + push filters to SQL) + be-compute-auth #28 (loads the activity stream twice) — same fetch-once fix; #23's SQL-filter push-down kept. (8) PERF-025 = backend-read #25 + be-compute-auth #31 (identical per-request auth DB-resolution caching keyed on the credentials-file signature). NOT merged but flagged as overlapping PERF-001's landing-path deferral: PERF-011 (SHA-1), PERF-013 (owners_filter.json parse), PERF-014 (solar eager load) — kept separate because each is a distinct deeper per-asset fix that still applies on the first-Explore path after PERF-001 defers them. Tiering: high/medium certainty → main (PERF-001..034); low certainty → speculative appendix (PERF-035..042), which includes the login-throttle locking item (PERF-040, a correctness/robustness fix, not a perf gain) and the two recommend-no-change puller items (PERF-041/042).

---

## 6. Hand-off — how to apply these

This report is designed to be re-fed as instructions. To act on a finding:

1. **Pick a finding** (start with the [§1.3 quick-win shortlist](#13-quick-win-shortlist) or a headline win).
2. **Paste its whole block** — Location + What & why + Execution + Behavior risk & rollback — back to Claude as the task. The **Execution** field is the implementation spec; the **Behavior risk & rollback** field is the safety contract.
3. **Honor the rail flag** if present — those keep the fix inside a locked decision (tenant scoping, owners-index schema versioning, single-place coalesce, ADR-051, EPSG:4326, etc.).
4. **Verify with the finding's own "confirm-it measurement."** Findings that ship a fix should bring their own tests per the normal TDD posture (out of scope for this report). For ETL/index changes, prefer the project's byte-identical / column-hash parity check before deleting the old path.
5. **Batch by effort:** the ⚡ quick-wins are safe to land together in one reviewed PR; 🔧 small and 🏗️ larger-refactor items deserve their own PR each.

**Suggested sequencing:** (a) the front-end cold-load cluster PERF-001 → 004 → 012 → 013/014 (they compound: split makes deferral effective at chunk granularity); (b) the slider-debounce pair PERF-002/003 + the map no-op guard PERF-010 + StatStrip count PERF-007 (one interaction-perf PR); (c) the backend read quick-wins PERF-005/006/008/009 (one PR, all measured); (d) ETL wins led by PERF-016 (the measured-largest ETL lever), then 020/021/028/029, with PERF-015 reframed as the scoring step's own speedup; (e) pullers PERF-031/032 if the desktop tool's idle jank is ever felt.

**Do not** apply PERF-019 (production Caddy config) as part of a code PR — it is a deploy-side work order, flagged report-only / do-not-deploy, to be applied deliberately against the production edge with its own review.

