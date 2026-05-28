# Map app — architecture

The analytical map app for the ground-lease pilot. Catalog-driven: it
binds to the preprocess output, never to a hardcoded state, so any state
that composes appears with zero app changes.

> Replaces the v1 Leaflet prototype (retired; in git history). Design locked in [ADR-030](../docs/adr/0030-map-app-v2-stack.md); shipped 2026-05-21.

## Stack

| Concern | Choice |
|---|---|
| Framework | Svelte 5 (runes) + Vite 8 + TypeScript |
| Map | MapLibre GL JS 5 + a keyless raster basemap (Carto Positron) |
| Parcel base layer | PMTiles vector tiles (tippecanoe-built) |
| Filter / search | DuckDB-WASM over a slim per-state parquet |
| Tests | Vitest (unit) + Playwright (E2E, Chromium + WebKit) |

## Data contract

The app reads, from one origin under `/data/processed/composite/`:

- `index.json` — the state list + bbox + counts (the `--app-assets`
  writer produces it). The app boots from this; no per-state probing.
- `<fips>/catalog.json` — per-state layer/view manifest + field schema.
- `<fips>/summary.json` — headline counts for the summary card.

`src/lib/schema.ts` pins the v3 composite field names. If a future
compose renames a field, that one file fails `npm run check` — drift is
caught at build time, not as a blank detail panel.

## Three map data layers

1. **Catalog GeoJSON** — towers, distress overlays, solar facilities and
   the five interestingness views. Loaded as MapLibre GeoJSON sources;
   heavy views lazy-load on first toggle.
2. **Parcel base layer** — `<fips>/parcels.pmtiles` vector tiles (2.1 M AR
   / 920 K MT parcels), discovered by convention, read over HTTP Range.
   12 attributes are baked into the tiles for instant click/paint.
3. **County choropleth** — `<fips>/county_boundaries.geojson`, shaded by
   ARC distress tier at low zoom; parcels fade in and take over at z ≥ 10.

## Filter & search engine

DuckDB-WASM range-queries `<fips>/parcels_attr.parquet` — the slim
attribute-only parquet (geometry + internal columns dropped, sorted by
interestingness score). `<fips>/facets.json` (precomputed distinct values
+ ranges) renders the filter controls without a query.

- `src/lib/query.ts` — `composeWhere` turns the filter state into SQL
  (unit-tested byte-for-byte; string literals escaped, numbers validated).
- A filter → DuckDB count + matching parcel ids → batched
  `setFeatureState` → the parcels layer fades non-matches.
- Owner search (`ILIKE`) and APN lookup hit the same parquet.
- Clicking any parcel fetches its full row from DuckDB to fill the panel.

## Serving

The app fetches root-relative `/data/...`. **`python -m http.server`
will not work** — PMTiles and DuckDB-WASM need HTTP Range / 206 responses
and it does not send them. Use the range-capable `scripts/serve.py`.

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
│   ├── App.svelte           layout, boot, URL sync, keyboard shortcuts
│   ├── components/          MapView + the sidebar panels + DetailsPanel
│   └── lib/                 catalog, schema, data, stores (Svelte state),
│                            duckdb, query, filters, facets, url, geo,
│                            format, palette
└── tests/
    ├── unit/                Vitest — pure logic
    └── e2e/                 Playwright — against the built app
```

The app's data inputs are produced by the preprocess pipeline — see
`scripts/preprocess/` (`tiles.py`, `facets.py`, `county_boundaries.py`,
`app_assets.py`) and run with `python scripts/preprocess.py --app-assets`
(+ `--tiles`).
