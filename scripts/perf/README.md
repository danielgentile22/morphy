# Map-app perf-probe

A committed, repeatable harness for the **map-app performance** baseline
(PRD [#163](https://github.com/danielgentile22/infra-lease-analytics/issues/163),
task [#164](https://github.com/danielgentile22/infra-lease-analytics/issues/164)).
It reproduces the Step-0 measurement so the end-of-PRD per-category deltas
(A–F) are computed **identically** to the baseline — the contract
[#169](https://github.com/danielgentile22/infra-lease-analytics/issues/169)
re-runs to report % improvement.

> **Local-only, relative numbers.** Everything here runs against the local dev
> stack and emits only sizes / timings / counts — **never PII, never prod data.**
> These are *relative* numbers for like-for-like comparison, not prod absolutes
> (dev bundle is unminified; prod adds gzip + a per-request auth gate + CDN RTT
> that the local harness deliberately excludes).

## What it measures

The metrics that define the acceptance bar (PRD §"Baseline & target metrics"):

| # | Category | Metric | Source in this harness |
|---|---|---|---|
| **A** | Time-to-first-tower (Explore cold) | `timeToFirstTowerMs` + feature count | `map_app_probe.js` (the `perf:towers` User-Timing measure) |
| **B** | DuckDB-WASM cold init (isolated) | `duckdbColdInitMs` | `duckdb_cold_init.js` (throwaway instance) |
| **A** | Tower load (probe+union+marshal) | `timeToFirstTowerMs − duckdbColdInitMs` | derived |
| **F** | `owners_filter.json` transfer / parse / count | `ownersFilter.*` | `map_app_probe.js` |
| **C** | Tower-path request count (parquet GET + HEAD) | request count | chrome-devtools **Network panel** (see below) |
| **E** | `parcels.pmtiles` on-disk size per state | MiB per state + total | `pmtiles_sizes.py` |
| **D**/initial | Parcel-tile count at the initial view | tile request count | chrome-devtools **Network panel** |

Files:

- `map_app_probe.js` — browser probe, Explore pass (A timing, feature count, F, request *views*).
- `duckdb_cold_init.js` — browser probe, isolated DuckDB cold-init pass (B).
- `pmtiles_sizes.py` — filesystem `parcels.pmtiles` sizes (E). `python scripts/perf/pmtiles_sizes.py [--json]`.
- `baseline-2026-06-13.json` — the **recorded baseline** (2026-06-13 numbers from the PRD). The contract #169 diffs against.

The browser probes read a passive User-Timing measure the app emits — see
`app/src/lib/perf.ts` (`markTowersStart` / `markTowersDone` bracket the tower
critical path in `stores.svelte.ts loadTowers()`). The measure brackets
**whatever the tower-load seam is** (today the DuckDB union; after PR3 the
`towers.json` fetch), so #169 compares the same span. The isolated cold-init
uses `duckDb`'s dev-only `window.__probeColdInit` handle (`app/src/lib/duckdb.ts`,
DEV builds only).

## 1. Prerequisites — start the local stack

Three servers, from the repo root, each in its own terminal:

```bash
# once, if the dev DB doesn't exist yet (Alembic, PRD #134) — creates
# data/processed/lead_state.sqlite3 (git-ignored) and seeds the dev/dev login:
AUTH_DEV_MODE=1 .venv/bin/alembic -c backend/alembic.ini upgrade head

# (1) Lead write-layer backend — dev auth (built-in dev/dev login):
AUTH_DEV_MODE=1 .venv/bin/uvicorn backend.app.main:app --port 8000

# (2) range-capable data server (serves /data over HTTP Range):
.venv/bin/python scripts/serve.py 8765

# (3) the map app (Vite proxies /data → :8765 and /api → :8000):
cd app && npm run dev          # http://localhost:5173
```

Requires composed data on disk (`data/processed/composite/<fips>/…` with
`parcels.pmtiles`, `towers.parquet`, `owners_filter.json`, `index.json`). The
heavy map load only fires on the `#/explore` route.

## 2. Pin the methodology (must match the baseline)

- Signed in as the **dev credential** (`dev` / `dev`).
- **`#/explore` cold reload**, Chrome via the chrome-devtools MCP, Apple silicon.
- **No** network throttle. **No** gzip (dev server sends none).
- **Cache state is the load-bearing variable** — control it explicitly:
  - For a *fully cold* load (real transfer sizes, cold DuckDB), reload with
    **cache disabled** (`navigate_page` `ignoreCache: true`).
  - The **cold-init** number depends on whether the ~6 MB WASM is already in
    the HTTP cache: empty cache ⇒ includes the fetch (higher); primed cache ⇒
    compile + instantiate only (≈ the PRD's 375 ms). Pick one and keep it
    consistent between baseline and re-measure.
- **Clear `localStorage` before the Explore reload** so the initial view is the
  deterministic all-anchors `fitBounds` framing (the `map.lastView` /
  pinned-home view would otherwise move the camera and change the parcel-tile
  count). The dev/dev user has no pinned home, so clearing storage is enough.
- Dev-bundle **LCP / DOMContentLoaded are excluded** (unminified, not representative).

## 3. Run it

### Pass A — isolated DuckDB cold-init (category B)

Measure this on the **Dashboard** (`#/`), where the app hasn't touched DuckDB
yet, so the throwaway instance is the first WASM instantiate on the page = cold.

1. `new_page` → `http://localhost:5173/#/` (an isolated context keeps a clean
   cookie/storage jar).
2. Sign in `dev` / `dev` (`fill_form` the username/password, click **Sign in**).
3. `evaluate_script` with the **contents of `duckdb_cold_init.js`**. Record
   `duckdbColdInitMs`.

### Pass B — Explore cold reload (categories A, C, F, parcel tiles)

4. `evaluate_script`: `() => { localStorage.clear(); return true; }`.
5. `navigate_page` (type `url`) → `http://localhost:5173/#/explore`.
6. `navigate_page` (type `reload`, `ignoreCache: true`) — the cold Explore boot.
7. Wait for the tower load to settle (poll until the `perf:towers` measure
   exists):
   ```js
   async () => { const d = Date.now()+20000;
     while (Date.now()<d) { const m = performance.getEntriesByName('perf:towers','measure').slice(-1)[0];
       if (m) return {ready:true, ms:Math.round(m.duration), features:m.detail&&m.detail.features};
       await new Promise(r=>setTimeout(r,200)); } return {ready:false}; }
   ```
8. `evaluate_script` with the **contents of `map_app_probe.js`**. Record
   `timeToFirstTowerMs`, `towerFeatureCount`, and `ownersFilter.*`.
9. **Request counts (categories C + parcel tiles)** — `list_network_requests`
   (`resourceTypes: ["fetch","xhr","other"]`), then count:
   - **tower-path** = requests whose URL contains `towers.parquet` (the 4 HEAD
     presence-probes + the 4 DuckDB-worker range GETs). The Network panel is
     authoritative here because **DuckDB issues its parquet GETs from a Web
     Worker**, which the in-page `performance` timeline does *not* see (the
     probe's `towerPathRequestsMainThread` only counts the 4 main-thread HEADs).
   - **parcel tiles** = requests whose URL contains `parcels.pmtiles` at the
     settled initial view.

### Pass C — tile sizes (category E)

10. `python scripts/perf/pmtiles_sizes.py` (add `--json` for machine-readable).

## 4. Reading the result / computing deltas

- **A (time-to-first-tower):** `timeToFirstTowerMs`. Breakdown =
  `duckdbColdInitMs` (B) + the remainder (probe + union + marshal).
- **B:** `duckdbColdInitMs`. Target: 0 ms on the tower path (DuckDB deferred to
  first parcel click) — i.e. after PR3 the tower path no longer inits DuckDB.
- **C:** tower-path request count from the Network panel. Target: 1 GET (+1 probe).
- **E:** `pmtiles_sizes.py` total vs baseline 1,679 MiB.
- **F:** `ownersFilter.transferMs` (cold) + `parseMs`; target ≈ 0 ms added wait
  (prefetched during the Dashboard).

#169 re-runs this harness and reports **% improvement per category** against
`baseline-2026-06-13.json`. Categories that miss target must be explained.

## 5. Stability

Run-to-run, the **deterministic** metrics are exact and are the comparison
anchors: tower feature count, owner count, `owners_filter` byte size, and the
tower-path request count. **Timing** metrics (ms) fluctuate with cache state and
machine load — keep the cache state fixed (§2) and compare like-for-like; treat
ms as relative, not absolute.

> **Local reproduction (2026-06-14, this machine) — validates the harness, not
> the contract.** Two cold Explore reloads gave *identical* deterministic
> metrics: `towerFeatureCount` 80,814; `ownerCount` 16,237;
> `owners_filter` encoded body 10,891,484 B; tower-path main-thread HEADs 4;
> parcel tiles 8 (clean run). `pmtiles_sizes.py` reported AR 313.6 / FL 789.2 /
> MT 306.1 / WV 270.2 = **1,679.1 MiB** total — matching the PRD's
> 314/789/306/270 = 1,679 MiB. Timings landed in the same order of magnitude as
> the PRD baseline (cold-init ≈ 0.5 s incl. the cold WASM fetch; tower critical
> path ≈ 1–1.7 s under a cache-busting reload). The 2026-06-13 PRD numbers
> remain the recorded baseline of record (`baseline-2026-06-13.json`).
