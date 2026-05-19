# ARCHITECTURE — How the system fits together

**Last updated:** 2026-05-19
**Audience:** engineers (human or AI) who need to understand or extend
the code without reading every file.

This doc describes what's *implemented today*. Future-state designs live
in [ROADMAP.md](./ROADMAP.md) and [MAP_APP_REHAUL.md](./MAP_APP_REHAUL.md).
Design decisions are locked in [DECISIONS.md](./DECISIONS.md).

---

## 1. System overview

Three loosely-coupled subsystems plus a shared on-disk data layout:

```
┌──────────────────────┐    raw/   ┌──────────────────────┐  normalized/  ┌──────────────────────┐
│  app_puller/         │──────────▶│  scripts/preprocess/ │──────────────▶│  app/  (map browser) │
│   PySide6 desktop UI │           │   Normalize → Join → │  composite/   │   Leaflet static SPA │
│   data fetcher       │           │   View → Compose     │               │                      │
└──────────────────────┘           └──────────────────────┘               └──────────────────────┘
        │                                    │                                    │
        ▼                                    ▼                                    ▼
   data/raw/<src>/current/            data/processed/                       browser only
   data/manifest.json                  ├── normalized/<src>/
                                       │   ├── raw.parquet
                                       │   ├── <type>.parquet (+ geojson)
                                       │   └── quality_report.json
                                       ├── composite/<fips>/
                                       │   ├── catalog.json
                                       │   ├── summary.json
                                       │   ├── parcels.parquet (+ geojson)
                                       │   ├── towers.parquet (+ geojson)
                                       │   ├── solar_facilities.parquet (…)
                                       │   ├── distress_overlays.parquet (…)
                                       │   ├── county_scores.parquet
                                       │   └── views/<name>.parquet (+ geojson)
                                       └── preprocess_manifest.json
```

Each subsystem is independently runnable: the puller doesn't need
preprocess installed; preprocess doesn't need the map app; the map
app reads static files written by preprocess.

---

## 2. Subsystem 1 — The data puller (`app_puller/`, `scripts/fetch/`)

A PySide6 desktop application that fetches ~28 raw data sources into
`data/raw/<source_id>/current/`.

### 2.1 Source contract

Every source subclasses `fetch.base.DataSource` and declares:

- **Metadata:** `id`, `name`, `category`, `coverage`, `cadence`,
  `description`, `legal` (LegalInfo), `estimated_size_mb`.
- `remote_version() -> str` — cheap probe (HEAD / metadata JSON) that
  returns a string that changes when upstream releases new data.
- `fetch(dest_dir, progress) -> FetchResult` — actually downloads.
- `validate(files)` — sanity-check downloaded artifacts.

Sources never touch the manifest or storage layout themselves —
`fetch.puller.fetch_one()` owns that.

### 2.2 Automation policy (legal contract)

Every source declares an `AutomationPolicy`. The puller **enforces** it:

| Policy | Puller behavior |
|---|---|
| `ALLOWED` | Auto-pulls. Publisher provides explicit bulk endpoint. |
| `TOLERATED` | Auto-pulls (single GET, identifying User-Agent). |
| `MANUAL_ONLY` | Never auto-pulls. UI shows walkthrough modal + deep link. |
| `CREDENTIALED` | Only pulls when env vars are set; otherwise like MANUAL_ONLY. |

This is a hard contract: future Claude must not "fix" a MANUAL_ONLY
source by adding scraping unless the publisher's terms have actually
changed.

### 2.3 Storage layout + atomicity

- Each source's raw data lives at `data/raw/<source_id>/current/`.
- Downloads land first in `data/raw/<source_id>/.partial/`, promoted
  atomically to `current/` only after `validate()` passes.
- **Current-only versioning** (ADR-004): no history retained on disk.
- All manifest writes go through `Manifest.save()` (write to temp,
  atomic rename).

### 2.4 Manifest

`data/manifest.json` is the single source of truth for "what we have on
disk." Per source:

```json
{
  "local_version": "...", "remote_version": "...",
  "fetched_at": "...", "checked_at": "...",
  "bytes": 0, "files": [...],
  "status": "ok|stale|missing|check_failed|fetch_failed|manual_only|needs_credentials",
  "error": null | "...",
  "next_recommended_check_at": "..."   // added in puller v2 overhaul
}
```

### 2.5 Puller UI

`app_puller/main_window.py` shows a category-grouped tree of every
registered source with status, size, version, and a primary action.
Top action bar:

- **Check for updates** — parallel HEAD across all sources.
- **Pull all stale / missing** — sequential auto-fetch (auto-policy
  sources only).
- **Rescan disk** — finds manually-dropped files.
- **Verify contents** — runs `scripts/verify_raw.py` per source.
- **Preprocess** — opens the per-state preprocess dialog.

Walkthrough modal (added in puller overhaul, Section 3 of work plan)
surfaces step-by-step download instructions for MANUAL_ONLY sources.

### 2.6 Headless reuse

The `scripts/fetch/` package is intentionally Qt-free. The puller is
just the UI layer on top — a CLI or scheduled job could call
`fetch.puller.fetch_one()` directly without touching PySide6.

---

## 3. Subsystem 2 — The preprocess pipeline (`scripts/preprocess/`)

A registry-driven pipeline that turns raw downloaded data into
canonical-schema parquet outputs, then composes per-state joined
outputs for the map app.

### 3.1 Three extension points

| Extension | File location | Add via | Purpose |
|---|---|---|---|
| **Normalizer** | `scripts/preprocess/normalizers/<source>.py` | `@register_normalizer` | One per raw source. Reads raw → emits canonical parquet(s). |
| **Join** | `scripts/preprocess/joins/<name>.py` | `@register_join` | Mutates one canonical layer with attributes from another. |
| **View** | `scripts/preprocess/views/<name>.py` | `@register_view` | Derived dataset for the map app or analytics. |

Each registered class is imported via `scripts/preprocess/registry.py`,
which triggers the decorator. The Composer reads from the registries —
no glue code per addition.

### 3.2 Canonical types

Defined in `scripts/preprocess/base.py` (`CURRENT_SCHEMA_VERSIONS`):

**Spatial:** `tower`, `parcel`, `distress_overlay`, `solar_facility`,
`billboard`, `address_point`.

**Tabular:** `county_score`, `license`, `location`, `entity`,
`transfer`, `lease`, `distributed_pv`, `aggregation`, `model_prediction`.

Every record gets system columns: `_source`, `_processed_at`,
`_schema_version`, `_tenant_id`, `_quality_score`, `valid_from`,
`valid_to`.

### 3.3 Full-fidelity raw preservation

Every Normalizer writes both:

- `raw.parquet` — every column from the source, untouched (renamed
  only to legal Parquet names if necessary), all rows, no filtering.
- `<canonical_type>.parquet` — the canonical-schema view derived from
  the raw. May filter, rename, retype, derive columns.

Future questions ("what's in the source's hidden `_dor_remarks` field?")
get answered without re-downloading.

### 3.4 Geometry derivatives

Every polygon record gets:

- `geom_centroid` — for fast "show me on map" at low zoom
- `geom_area_m2` — for filtering / sorting
- `geom_bbox` — 4 floats; fast spatial pre-filtering
- `geom_simplified` — Douglas-Peucker simplified for huge layers

Every point record gets:

- `geom_h3_r8` — H3 index at resolution 8 (~0.7 km²) for fast
  clustering / density / proximity queries (when `h3` package present)

### 3.5 Composer

`scripts/preprocess/compose.py`. For one state FIPS:

1. Loads every canonical layer from `normalized/<source>/<type>.parquet`,
   filters to the state (via `state_fips` column or bbox fallback).
2. Runs all registered Joins in dependency order
   (`ordered_joins()` does the topo sort).
3. Runs all registered Views.
4. Writes per-canonical-type Parquet + GeoJSON (with huge-layer GeoJSON
   skip per ADR-023).
5. Writes per-state `catalog.json` (self-documenting layer manifest the
   map app reads).
6. Writes per-state `summary.json` (counts + sources + joins + views +
   warnings).

### 3.6 Dual GeoParquet + GeoJSON output (ADR-003)

Every spatial output is written as both formats; for layers ≥ 100K
rows only the simplified-geometry GeoJSON is written. Parquet is
canonical for analytics; GeoJSON is for the legacy Leaflet app.

### 3.7 Owner clustering + interestingness score

Per-parcel post-processing:

- **`owner_cluster_id`** — SHA1 of `normalize_owner_name(name) + '|' +
  normalize_address(addr)`. Stable across runs.
- **`owner_kind`** — categorical inferred from owner-name patterns:
  `llc`, `individual`, `trust`, `corporation`, `gov`, `church`,
  `partnership`, `school`, `unknown`.
- **`interestingness_score`** — composite 0–1 score from
  infrastructure presence + distress + owner-kind weight + cluster
  size. Components in `scripts/preprocess/score.py`.

### 3.8 CLI

```bash
python scripts/preprocess.py                    # all sources + all states
python scripts/preprocess.py --state 05         # just AR
python scripts/preprocess.py --normalize-only
python scripts/preprocess.py --compose-only --state 12
python scripts/preprocess.py --force-rebuild
python scripts/preprocess.py --list-views
python scripts/preprocess.py --list-joins
python scripts/preprocess.py --list-states
python scripts/preprocess.py --source <id>             # added in Section 5.3
python scripts/preprocess.py --rebuild-manifest        # added in Section 4.5
```

Same code path is invoked by the puller's **Preprocess** button.

### 3.9 Manifest

`data/processed/preprocess_manifest.json` tracks per-source normalize
status (`ok` / `failed` / `skipped`) and per-state compose status. Used
for incremental skip when raw versions haven't changed.

`--rebuild-manifest` (ADR-022) re-derives this from on-disk files,
useful after interrupted runs.

---

## 4. Subsystem 3 — The map app (`app/`)

Static single-page Leaflet app. Loads composite outputs from
`data/processed/composite/<fips>/` via `fetch()`. No build step, no
framework.

### 4.1 Current capabilities

- **State selector** populated by probing `composite/<fips>/catalog.json`
  for all 50 state FIPS in parallel.
- **Layer toggles** — towers, parcels, opportunity zones (legacy name;
  v3 calls this `distress_overlays`).
- **View toggles** — auto-rendered from `catalog.json` `views` field.
  Each view loads as a separate Leaflet layer.
- **Filters** — "only parcels with towers", "only parcels in OZ",
  tower-owner dropdown, ULS-carrier dropdown.
- **Details panel** — click feature → renders attribute table.

### 4.2 Known limitations of v1 map app

Documented in [LIMITATIONS.md](./LIMITATIONS.md):

- Title bar hard-coded to "Graham County, NC".
- Cannot load huge parcel GeoJSONs (AR 3.6 GB, IN 5.6 GB).
- No filters for v3 schema fields (`owner_kind`,
  `interestingness_score`, `owner_cluster_size`, `distress_tier`).
- No virtualized top-N list, no owner search.
- Single per-state load (no cross-state view).

### 4.3 Future-state

The full rebuild is scoped in
[MAP_APP_REHAUL.md](./MAP_APP_REHAUL.md). Marked DEFERRED. Tech stack
locked in ADR-030 (MapLibre + PMTiles + DuckDB-WASM + Svelte).

---

## 5. Shared on-disk layout

```
data/
├── raw/<source_id>/current/         Latest raw per source
├── manifest.json                    Fetch manifest (puller-owned)
├── fetch.log                        JSONL event log (puller-owned)
└── processed/
    ├── normalized/<source>/         Canonical-schema parquet + raw.parquet
    │   ├── raw.parquet
    │   ├── <canonical_type>.parquet
    │   ├── <canonical_type>.geojson
    │   └── quality_report.json
    ├── composite/<state_fips>/      Per-state joined outputs
    │   ├── catalog.json
    │   ├── summary.json
    │   ├── parcels.parquet / .geojson
    │   ├── towers.parquet / .geojson
    │   ├── solar_facilities.parquet / .geojson
    │   ├── distress_overlays.parquet / .geojson
    │   ├── county_scores.parquet
    │   └── views/<name>.parquet / .geojson
    └── preprocess_manifest.json     Preprocess manifest
```

`data/` is git-ignored. Composite outputs total a few GB across the
anchor states.

---

## 6. Catalog format (the map-app contract)

Each state's `composite/<fips>/catalog.json`:

```json
{
  "state_fips": "05",
  "state_abbr": "AR",
  "state_name": "Arkansas",
  "generated_at": "2026-05-18T22:25:00Z",
  "schema_version": 3,
  "sources_used_versions": {        // added in Section 5.5
    "ar_parcels": "manual",
    "fcc_asr": "2026-05-18",
    "faa_oeaaa": "2026-05-15"
  },
  "layers": {
    "parcels": {
      "canonical_type": "parcel",
      "rows": 2116976,
      "parquet_path": "parcels.parquet",
      "geojson_path": "parcels.geojson",
      "schema": { /* field type summary */ }
    },
    "towers": { … },
    "solar_facilities": { … },
    "county_scores": { … }
  },
  "views": {
    "llc_owned_parcels_with_infra": {
      "rows": 1164,
      "description": "LLC-owned parcels hosting at least one tower or solar facility",
      "parquet_path": "views/llc_owned_parcels_with_infra.parquet",
      "geojson_path": "views/llc_owned_parcels_with_infra.geojson",
      "inputs": ["parcel"]
    },
    "interestingness_top_1000": { … },
    "owner_clusters": { … },
    …
  },
  "warnings": []
}
```

The map app reads only `catalog.json` to discover what's available
for a state — adding a new View at preprocess time produces a new
toggle in the UI with zero JS changes.

---

## 7. Code conventions

- **Headless `fetch/`.** No PySide6 imports inside `scripts/fetch/`.
  Qt lives only in `app_puller/`.
- **Atomic writes everywhere.** Download to `.partial`, rename.
  Manifest writes go through `Manifest.save()` (temp + rename).
- **Preprocess outputs EPSG:4326.** Every spatial output reprojected
  to WGS84 lat/lon.
- **Sparse comments.** Comments where the *why* is non-obvious; not
  where the code self-documents.
- **No new normalize-time filtering.** Per ADR (full-fidelity raw
  preservation): keep all rows; add status / validity columns; let
  Joins and Views filter.

---

## 8. Where to look

| Question | File |
|---|---|
| What is the project? | [PROJECT_BRIEF.md](../PROJECT_BRIEF.md) |
| What's in scope right now? | [SCOPE.md](./SCOPE.md) |
| What does success look like? | [GOALS.md](./GOALS.md) |
| What works today? | [STATUS.md](./STATUS.md) |
| Past / future arc? | [ROADMAP.md](./ROADMAP.md) |
| Locked design choices? | [DECISIONS.md](./DECISIONS.md) |
| Per-source detail? | [DATA_SOURCES.md](./DATA_SOURCES.md) |
| When does each source need a refresh? | [DATA_FRESHNESS.md](./DATA_FRESHNESS.md) |
| Caveats + pre-commercial blockers? | [LIMITATIONS.md](./LIMITATIONS.md) |
| PII / data-handling? | [SECURITY.md](./SECURITY.md) |
| Glossary of terms? | [GLOSSARY.md](./GLOSSARY.md) |
| Future map app? | [MAP_APP_REHAUL.md](./MAP_APP_REHAUL.md) |
| Test strategy? | [TESTING.md](./TESTING.md) |
| Puller UX design? | [PULLER_UX.md](./PULLER_UX.md) |
