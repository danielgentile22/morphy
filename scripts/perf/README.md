# Map-app perf-probe

A committed, repeatable harness for the **map-app performance** baseline,
built for the map-app performance plan. It reproduces the initial
measurement, so the per-category deltas (A-F) at the end of that work come
out **identically** to the baseline. The re-measure re-runs this harness to
report % improvement.

> **Local-only, relative numbers.** Everything here runs against the local dev
> stack and emits only sizes, timings and counts: **never PII (personally
> identifiable information), never deployed data.** These are *relative*
> numbers for like-for-like comparison, not absolutes for the deployed app.
> The dev bundle is unminified, and the deployed app adds gzip, a per-request
> auth gate and CDN round-trip time, all of which the local harness
> deliberately excludes.

## What it measures

The metrics that defined the plan's acceptance bar:

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

- `map_app_probe.js`: browser probe, Explore pass (A timing, feature count, F, request *views*).
- `duckdb_cold_init.js`: browser probe, isolated DuckDB cold-init pass (B).
- `pmtiles_sizes.py`: filesystem `parcels.pmtiles` sizes (E). `python scripts/perf/pmtiles_sizes.py [--json]`.
- `baseline-2026-06-13.json`: the **recorded baseline** (the 2026-06-13 numbers). The re-measure diffs against it.

The browser probes read a passive User-Timing measure the app emits. See
`app/src/lib/perf.ts` (`markTowersStart` / `markTowersDone` bracket the tower
critical path in `stores.svelte.ts loadTowers()`). The measure brackets
**whatever the tower-load seam is**, so the re-measure compares the same span.
At baseline time that seam was the DuckDB union. The `towers.json` fetch later
replaced it, with DuckDB kept as the fallback. The isolated cold-init uses
`duckDb`'s dev-only `window.__probeColdInit` handle (`app/src/lib/duckdb.ts`,
DEV builds only).

## 1. Prerequisites: start the local stack

Three servers, from the repo root, each in its own terminal:

```bash
# once, if the dev DB doesn't exist yet (Alembic): creates
# data/processed/lead_state.sqlite3 (git-ignored) and seeds the dev/dev login
AUTH_DEV_MODE=1 .venv/bin/alembic -c backend/alembic.ini upgrade head

# (1) Lead write-layer backend, dev auth (built-in dev/dev login):
AUTH_DEV_MODE=1 .venv/bin/uvicorn backend.app.main:app --port 8000

# (2) range-capable data server (serves /data over HTTP Range):
.venv/bin/python scripts/serve.py 8765

# (3) the map app (Vite proxies /data → :8765 and /api → :8000):
cd app && npm run dev          # http://localhost:5173
```

It needs composed data on disk (`data/processed/composite/<fips>/…` with
`parcels.pmtiles`, `towers.parquet`, `owners_filter.json`, `index.json`). The
heavy map load fires only on the `#/explore` route.

## 2. Pin the methodology (must match the baseline)

- Signed in as the **dev credential** (`dev` / `dev`).
- **`#/explore` cold reload**, Chrome via the chrome-devtools MCP, Apple silicon.
- **No** network throttle. **No** gzip (the dev server sends none).
- **Cache state is the load-bearing variable.** Control it explicitly:
  - For a *fully cold* load (real transfer sizes, cold DuckDB), reload with
    **cache disabled** (`navigate_page` `ignoreCache: true`).
  - The **cold-init** number depends on whether the ~6 MB WASM is already in
    the HTTP cache. An empty cache includes the fetch (higher). A primed cache
    measures compile + instantiate only (≈ the 375 ms baseline). Pick one and
    keep it consistent between baseline and re-measure.
- **Clear `localStorage` before the Explore reload** so the initial view is the
  deterministic all-anchors `fitBounds` framing. Otherwise the `map.lastView` or
  pinned-home view moves the camera and changes the parcel-tile count. The
  dev/dev user has no pinned home, so clearing storage is enough.
- Dev-bundle **LCP / DOMContentLoaded are excluded** (unminified, not representative).

## 3. Run it

### Pass A: isolated DuckDB cold-init (category B)

Measure this on the **Dashboard** (`#/`). The app hasn't touched DuckDB there
yet, so the throwaway instance is the first WASM instantiate on the page, which
makes it cold.

1. `new_page` → `http://localhost:5173/#/` (an isolated context keeps a clean
   cookie/storage jar).
2. Sign in `dev` / `dev` (`fill_form` the username/password, click **Sign in**).
3. `evaluate_script` with the **contents of `duckdb_cold_init.js`**. Record
   `duckdbColdInitMs`.

### Pass B: Explore cold reload (categories A, C, F, parcel tiles)

4. `evaluate_script`: `() => { localStorage.clear(); return true; }`.
5. `navigate_page` (type `url`) → `http://localhost:5173/#/explore`.
6. `navigate_page` (type `reload`, `ignoreCache: true`). This is the cold Explore boot.
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
9. **Request counts (categories C + parcel tiles).** Run `list_network_requests`
   (`resourceTypes: ["fetch","xhr","other"]`), then count:
   - **tower-path** = requests whose URL contains `towers.parquet` (the 4 HEAD
     presence-probes + the 4 DuckDB-worker range GETs). The Network panel is
     authoritative here because **DuckDB issues its parquet GETs from a Web
     Worker**, which the in-page `performance` timeline does *not* see. The
     probe's `towerPathRequestsMainThread` counts only the 4 main-thread HEADs.
   - **parcel tiles** = requests whose URL contains `parcels.pmtiles` at the
     settled initial view.

### Pass C: tile sizes (category E)

10. `python scripts/perf/pmtiles_sizes.py` (add `--json` for machine-readable output).

## 4. Reading the result and computing deltas

- **A (time-to-first-tower):** `timeToFirstTowerMs`. Breakdown =
  `duckdbColdInitMs` (B) + the remainder (probe + union + marshal).
- **B:** `duckdbColdInitMs`. Target: 0 ms on the tower path (DuckDB deferred to
  first parcel click). In other words, once `towers.json` replaced the DuckDB
  union, the tower path no longer inits DuckDB.
- **C:** tower-path request count from the Network panel. Target: 1 GET (+1 probe).
- **E:** `pmtiles_sizes.py` total vs baseline 1,679 MiB.
- **F:** `ownersFilter.transferMs` (cold) + `parseMs`. Target: ≈ 0 ms added wait
  (prefetched during the Dashboard).

The re-measure re-runs this harness and reports **% improvement per category**
against `baseline-2026-06-13.json`. Any category that misses its target needs
an explanation.

## 5. Stability

Run to run, the **deterministic** metrics are exact, and they are the
comparison anchors: tower feature count, owner count, `owners_filter` byte
size, and the tower-path request count. **Timing** metrics (ms) fluctuate with
cache state and machine load. Keep the cache state fixed (§2), compare
like-for-like, and treat ms as relative, not absolute.

> **Local reproduction (2026-06-14).** This run validated the harness, not the
> targets. Two cold Explore reloads gave *identical* deterministic
> metrics: `towerFeatureCount` 80,814; `ownerCount` 16,237;
> `owners_filter` encoded body 10,891,484 B; tower-path main-thread HEADs 4;
> parcel tiles 8 (clean run). `pmtiles_sizes.py` reported AR 313.6 / FL 789.2 /
> MT 306.1 / WV 270.2 = **1,679.1 MiB** total, matching the baseline's
> 314/789/306/270 = 1,679 MiB. Timings landed in the same order of magnitude as
> the baseline (cold-init ≈ 0.5 s including the cold WASM fetch; tower critical
> path ≈ 1-1.7 s under a cache-busting reload). The 2026-06-13 numbers remain
> the recorded baseline (`baseline-2026-06-13.json`).
