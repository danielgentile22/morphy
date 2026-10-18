# Map app architecture

The analytical map app for morphy. It is data-driven: it binds to the
preprocess output (the composite `index.json` plus per-state assets), never
to a hardcoded state, so any state that composes appears with no app changes.

> Replaced the v1 Leaflet prototype (retired; in git history). Design locked in [ADR-030](../docs/adr/0030-map-app-v2-stack.md); shipped 2026-05-21.

## Stack

| Concern | Choice |
|---|---|
| Framework | Svelte 5 (runes) + Vite 8 + TypeScript |
| Map | MapLibre GL JS 5 + keyless Esri raster basemaps (Light Gray, Streets, Dark Gray); MapTiler Satellite Hybrid when `VITE_MAPTILER_KEY` is set |
| Parcel base layer | PMTiles vector tiles (tippecanoe-built) |
| Explore filter / search | One shared `FilterModel` over the slim owners index narrows both Explore lenses, the map and the ranked tower list (sidebar `FilterPanel` plus owner and Antenna Structure Registration (ASR) search) |
| Tests | Vitest (unit) + Playwright (E2E, Chromium + WebKit) |

## Data contract

The app reads, from one origin under `/data/processed/composite/`:

- `index.json`: the state list, bounding box and counts (the `--app-assets`
  writer produces it). The app boots from this, with no per-state probing.
  It then addresses per-state assets (towers, `parcels.pmtiles`, county
  boundaries, and so on) by convention.
- `<fips>/summary.json`: headline counts for the summary card. `<fips>` is
  the two-digit state Federal Information Processing Standards (FIPS) code.

`src/lib/schema.ts` pins the v3 composite field names. The
schema-completeness contract (`tests/unit/schema-completeness.test.ts`)
reads each composite's `<fips>/catalog.json` layer schema and fails
`npm run test:unit` if a future compose renames or drops a field. CI catches
the drift, so it never shows up as a blank detail panel. (The app itself no
longer parses `catalog.json` at runtime.)

A tower's `carriers` field holds the spectrum licensees that the carrier
join (from the FCC Universal Licensing System, ULS) attaches to every tower.
It is a list-of-struct, not a scalar, so the app special-cases it instead of
rendering a flat row. One shared `CarrierList.svelte` (confidence badges,
tooltips, empty state) renders it on **both** tower surfaces. The first is
the `LeadPage` holdings, where a structures-first tower click lands, served
by the backend. The second is the schema-driven `DetailsPanel` tower panel
(the catalog `towers` layer). A `TOWER_SCHEMA` entry keeps `carriers` under
the schema-completeness contract. `parseCarriers` accepts the GeoJSON array,
the DuckDB JSON string, and the backend's already-parsed JSON.

## Three map data layers

1. **Catalog GeoJSON.** Towers, distress overlays, solar facilities and
   the catalog views: one interestingness view (`interestingness_top_1000`)
   plus segment and summary views (see `<fips>/catalog.json` for the full set).
   They load as MapLibre GeoJSON sources, and heavy views lazy-load on first
   toggle.
2. **Parcel base layer.** `<fips>/parcels.pmtiles` vector tiles (2.1 M AR
   and 920 K MT parcels), discovered by convention and read over HTTP Range.
   The tiles carry 12 baked-in attributes for instant click and paint.
3. **County choropleth.** `<fips>/county_boundaries.geojson`, shaded by
   Appalachian Regional Commission (ARC) distress tier at low zoom. Parcels
   fade in and take over at z ≥ 10.

## Explore filter and search

Triage filtering is **lead-centric** but lives in **Explore**. One shared
`FilterModel` narrows **both Explore lenses** from the same state: the
structures-first map's tower layer **and** Explore's ranked tower list. (The
Leads worklist is a separate surface, sorted by score, and does not use this
filter.) The old parcel-centric sidebar (acreage, raw "has tower", per-parcel
ranking) is retired. In its place is one vertical `FilterPanel` of
collapsible filter sections, plus an **owner-name/ASR search box**.

- `src/lib/filter-model.ts` is the deep module. A `FILTER_FIELDS` registry
  projects two ways from one source of truth: `composeOwnerWhere()` (a
  deterministic SQL string, **unit-tested byte-for-byte**, which is the query
  contract) and `matchesOwner()` (the runtime predicate both lenses use).
  Filter set: State (multi, **OR**), distress (ARC tier, Opportunity Zone
  (OZ), Qualified Census Tract (QCT), persistent poverty), structure type,
  score (**min threshold**), owner kind, portfolio size, total assessed value
  (range), county, tower height, active-only, structure count.
- `src/lib/filter-model.svelte.ts` holds the single live `model` and the slim
  owners index (`owners_filter.json`). It derives `matchingClusterIds` (the
  owner-id set the map narrows towers by), the control options and extents,
  and owner search.
- **Map**: each tower carries its owner's `display_cluster_id` (`cid`, baked in
  `towers.ts`). `filterTowers()` keeps only towers whose
  `cid ∈ matchingClusterIds`, then calls `setData`. **Ranked list**: narrows
  the same slim index (minus owners advanced past New) with the same
  predicate, ranked by score.
- Owner-name search opens the matching Lead. ASR search flies the map to the
  tower.

### Parcel base layer (PMTiles-only)

The parcel base layer is the PMTiles vector tiles alone (12 attributes baked in
for instant click and paint). The original DuckDB-WASM parcel filter over a
slim per-state parquet, and its parcel-centric sidebar (search and top-list),
were retired. The owner `FilterModel` above replaced them. (DuckDB-WASM
remains only as the tower-load fallback in `towers.ts`.)

## Serving

The app fetches root-relative `/data/...`. **`python -m http.server`
will not work.** PMTiles and DuckDB-WASM need HTTP Range / 206 responses,
and it does not send them. Use the range-capable `scripts/serve.py`.

**MapTiler Satellite basemap (the default).** `VITE_MAPTILER_KEY` is a
*client-side* key. It ships in the bundle, so MapTiler's HTTP-referrer
allowlist protects it, not secrecy. Even so, it stays out of git:

- **Dev:** put it in `app/.env` (git-ignored; `app/.env.example` documents
  it). Vite loads it into `import.meta.env`.
- **Deploy:** `deploy.sh` reads `VITE_MAPTILER_KEY` from the environment or
  the repo-root `.env` and passes it as `fly deploy --build-arg`. The
  `Dockerfile` `ARG VITE_MAPTILER_KEY` defaults to empty.

`src/lib/basemap.ts` sets `maptilerEnabled` from whether the key is non-empty.
With no key (CI builds, a fresh clone, a bare Docker build), the Satellite
option is hidden in settings and `basemapSource('satellite')` returns Esri
Dark Gray. A stored `satellite` preference, which is also the default in
`user-settings-store.svelte.ts`, therefore degrades to a keyless basemap, and
the map never requests MapTiler tiles it would be refused. MapTiler's free
tier is for non-commercial use only.

- **Dev:** `npm run dev` (Vite proxies `/data` → `scripts/serve.py` on
  :8765 and `/api` → the backend on :8000).
- **Built:** `npm run build` then `npm run preview` (a static server,
  also proxying `/data` and `/api`). The E2E suite runs against this.

MapLibre's worker loads from a `?url` asset via `setWorkerUrl`. Vite 8's
Rolldown bundler mis-compiles the worker if it bundles it inline (the
GeoJSON tiler throws `f is not defined`).

## Auth and the read-only demo

`auth-store.svelte.ts` owns the signed-in state. Besides the user and team,
it holds two flags from the backend
([ADR-077](../docs/adr/0077-read-only-demo-credential.md)):

- `auth.demoMode` comes from the public `GET /api/auth/config`. When true,
  `SignIn.svelte` shows "Explore the demo", which calls `POST /api/auth/demo`
  and gets the same httpOnly session cookie a password login gets. A failed
  config fetch leaves it off.
- `auth.readOnly` comes from `read_only` on `GET /api/auth/me`. When true, the
  user menu shows a "Read-only demo" badge and write controls (status changes,
  notes, attempts, tasks, scoring presets, settings saves) are hidden or disabled.
  Appearance preferences still apply for the visit, with no server write.

The backend is the real boundary. It refuses every write from a read-only
session with 403. `leads-api.ts` routes any 403 to the app-wide notice store
(`notice.svelte.ts`, rendered by `components/Notice.svelte`), which shows one
calm, self-dismissing message instead of a broken panel.

## Run

```bash
# from the repo root: the range-capable data server
python scripts/serve.py 8765

# from app/
npm install
npm run dev                      # http://localhost:5173
npm run check                    # svelte-check (type + a11y)
npm run test:unit                # Vitest
npm run test:e2e                 # Playwright (builds + previews the app)
npm run build                    # -> dist/  (not committed)
```

## Layout

```
app/
├── ARCHITECTURE.md          this file
├── index.html
├── src/
│   ├── App.svelte           shell + hash router, boot, URL sync, shortcuts
│   ├── components/          MapView + FilterPanel + DetailsPanel + the
│                            map-layer panels + the Lead surfaces
│                            (ExploreList / Leads / MyLeads / LeadPage / SignIn)
│   └── lib/                 catalog, schema, data, stores (Svelte state),
│                            duckdb, filters, url, geo, format, palette,
│                            towers, owner-cluster, filter-model (+ .svelte
│                            store), owners-filter-index, leads-api,
│                            leads-store, auth-store, notice, lead-status,
│                            basemap
└── tests/
    ├── unit/                Vitest: pure logic
    └── e2e/                 Playwright: against the built app
```

The preprocess pipeline produces the app's data inputs. See
`scripts/preprocess/` (`tiles.py`, `facets.py`, `county_boundaries.py`,
`app_assets.py`), run with `python scripts/preprocess.py --app-assets`
(+ `--tiles`).
