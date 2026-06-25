# Map app — architecture

The analytical map app for the ground-lease pilot. Catalog-driven: it
binds to the preprocess output, never to a hardcoded state, so any state
that composes appears with zero app changes.

> Replaces the v1 Leaflet prototype (retired; in git history). Design locked in [ADR-030](../docs/adr/0030-map-app-v2-stack.md); shipped 2026-05-21.

## Stack

| Concern | Choice |
|---|---|
| Framework | Svelte 5 (runes) + Vite 8 + TypeScript |
| Map | MapLibre GL JS 5 + keyless raster basemaps (Carto Positron/Voyager/Dark Matter); optional MapTiler Satellite Hybrid when `VITE_MAPTILER_KEY` is set |
| Parcel base layer | PMTiles vector tiles (tippecanoe-built) |
| Lead filter / search | One shared lead-centric `FilterModel` over the slim owners index (top bar + "More" popover + owner/ASR search — Slice 6 / #52) |
| Parcel base-layer filter | DuckDB-WASM over a slim per-state parquet (now UI-less — see below) |
| Tests | Vitest (unit) + Playwright (E2E, Chromium + WebKit) |

## Data contract

The app reads, from one origin under `/data/processed/composite/`:

- `index.json` — the state list + bbox + counts (the `--app-assets`
  writer produces it). The app boots from this; no per-state probing.
- `<fips>/catalog.json` — per-state layer/view manifest + field schema.
- `<fips>/summary.json` — headline counts for the summary card.

`src/lib/schema.ts` pins the v3 composite field names. The
schema-completeness contract (`tests/unit/schema-completeness.test.ts`)
fails `npm run test:unit` if a future compose renames or drops a field —
drift is caught in CI, not as a blank detail panel.

A tower's `carriers` (the ULS spectrum licensee(s) #24 put on every tower —
a list-of-struct, not a scalar) is special-cased rather than rendered as a
flat row: one shared `CarrierList.svelte` (confidence badges + tooltips +
empty state) renders it on **both** tower surfaces — the `LeadPage` holdings
(where a structures-first tower click lands, backend-served) and the
schema-driven `DetailsPanel` tower panel (the catalog `towers` layer).
`carriers` stays under the schema-completeness contract via a `TOWER_SCHEMA`
entry (Slice A / #28). `parseCarriers` accepts the GeoJSON array, the DuckDB
JSON-string, and the backend's already-parsed JSON forms.

## Three map data layers

1. **Catalog GeoJSON** — towers, distress overlays, solar facilities and
   the catalog views: one interestingness view (`interestingness_top_1000`)
   plus segment/summary views (see `<fips>/catalog.json` for the live set).
   Loaded as MapLibre GeoJSON sources; heavy views lazy-load on first toggle.
2. **Parcel base layer** — `<fips>/parcels.pmtiles` vector tiles (2.1 M AR
   / 920 K MT parcels), discovered by convention, read over HTTP Range.
   12 attributes are baked into the tiles for instant click/paint.
3. **County choropleth** — `<fips>/county_boundaries.geojson`, shaded by
   ARC distress tier at low zoom; parcels fade in and take over at z ≥ 10.

## Lead filter & search (the primary triage surface — Slice 6 / #52)

Triage filtering is **lead-centric**: one shared `FilterModel` narrows **both**
the structures-first map's tower layer **and** the Candidates list from the same
state. The cluttered parcel-centric sidebar (acreage, raw "has tower", per-parcel
ranking) is retired in favour of a slim **top filter bar + "More" popover** + an
**owner-name/ASR search box**.

- `src/lib/filter-model.ts` — the deep module. A `FILTER_FIELDS` registry
  projects two ways from one source of truth: `composeOwnerWhere()` (a
  deterministic SQL string, **unit-tested byte-for-byte** — the query contract)
  and `matchesOwner()` (the runtime predicate both surfaces use). Filter set:
  State (multi, **OR**), distress (ARC tier + OZ/QCT/persistent-poverty),
  structure type, score (**min threshold**), owner kind, portfolio size, total
  assessed value (range), county, tower height, active-only, structure count.
- `src/lib/filter-model.svelte.ts` — the single live `model` + the slim owners
  index (`owners_filter.json`), deriving `matchingClusterIds` (the owner-id set
  the map narrows towers by) + the control options/extents + owner search.
- **Map**: each tower carries its owner's `display_cluster_id` (`cid`, baked in
  `towers.ts`); `filterTowers()` keeps only towers whose `cid ∈ matchingClusterIds`,
  then `setData`. **Candidates**: filters the same slim index (minus owners
  advanced off New) with the same predicate, ranked by score.
- Owner-name search opens the matching Lead; ASR search flies the map to the tower.

### Parcel base-layer filter (now UI-less)

The original DuckDB-WASM parcel filter still backs the parcel base layer but no
longer has a UI surface (the parcel-centric `FilterPanel`/`SearchPanel`/`TopList`
were removed in Slice 6). It range-queries `<fips>/parcels_attr.parquet`:

- `src/lib/query.ts` — `composeWhere` turns the parcel filter state into SQL
  (unit-tested byte-for-byte; string literals escaped, numbers validated).
- A filter → DuckDB count + matching parcel ids → batched `setFeatureState`
  → the parcels layer fades non-matches.
- Clicking any parcel fetches its full row from DuckDB to fill the panel.

## Serving

The app fetches root-relative `/data/...`. **`python -m http.server`
will not work** — PMTiles and DuckDB-WASM need HTTP Range / 206 responses
and it does not send them. Use the range-capable `scripts/serve.py`.

**MapTiler Satellite basemap (the default).** `VITE_MAPTILER_KEY` is a
*client-side* key (it ships in the bundle), protected by MapTiler's
HTTP-referrer allowlist, not by secrecy — so it's **baked into the image as the
`Dockerfile` `ARG VITE_MAPTILER_KEY` default**; a bare deploy needs no arg. Dev:
put it in `app/.env.local` (git-ignored). Override with a different key via
`fly deploy --build-arg VITE_MAPTILER_KEY=…` (deploy.sh forwards `$VITE_MAPTILER_KEY`
when set). With no key anywhere (e.g. CI builds, which don't see the Dockerfile),
the Satellite option is hidden and any stored `satellite` pref degrades to Carto
Dark (never 403s). MapTiler's free tier is non-commercial / R&D; production
commercial use needs a paid plan (~$25/mo).

- **Dev:** `npm run dev` (Vite proxies `/data` → `scripts/serve.py` on
  :8765).
- **Built:** `npm run build` then `npm run preview` (a static server,
  also proxying `/data`). The E2E suite runs against this.

MapLibre's worker is loaded from a `?url` asset via `setWorkerUrl` —
Vite 8's Rolldown bundler mis-compiles the worker if it bundles it
inline (the GeoJSON tiler throws `f is not defined`).

## Run

```bash
# from the repo root — the range-capable data server
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
│   ├── components/          MapView + TopFilterBar + DetailsPanel + the
│                            map-layer panels + the Lead surfaces
│                            (Candidates / MyLeads / LeadPage / SignIn)
│   └── lib/                 catalog, schema, data, stores (Svelte state),
│                            duckdb, query, filters, facets, url, geo,
│                            format, palette, towers, owner-cluster,
│                            filter-model (+ .svelte store), owners-filter-index,
│                            leads-api, leads-store, auth-store, lead-status
└── tests/
    ├── unit/                Vitest — pure logic
    └── e2e/                 Playwright — against the built app
```

The app's data inputs are produced by the preprocess pipeline — see
`scripts/preprocess/` (`tiles.py`, `facets.py`, `county_boundaries.py`,
`app_assets.py`) and run with `python scripts/preprocess.py --app-assets`
(+ `--tiles`).
