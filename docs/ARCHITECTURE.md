# ARCHITECTURE — How the system fits together

**Last updated:** 2026-05-25
**Audience:** engineers (human or AI) who need to understand or extend the code without reading every file.

This doc describes what's *implemented today* plus the Phase 1 Slice 4 backend, which is a **locked design that is UNIMPLEMENTED** (no `backend/` code exists on disk as of 2026-05-29). Future-state designs live in [ROADMAP.md](./ROADMAP.md). Design decisions are locked under [docs/adr/](./adr/) — [DECISIONS.md](./DECISIONS.md) is the cross-doc index.

---

## 1. System overview

**Three loosely-coupled subsystems today, plus a Slice 4 backend in design** for write-layer features (lead state, lease docs, auth):

```
┌──────────────────────┐    raw/   ┌──────────────────────┐  normalized/  ┌──────────────────────┐
│  app_puller/         │──────────▶│  scripts/preprocess/ │──────────────▶│  app/  (map browser) │
│   PySide6 desktop UI │           │   Normalize → Join → │  composite/   │   Svelte + MapLibre  │
│   data fetcher       │           │   View → Compose     │               │   PMTiles + DuckDB   │
└──────────────────────┘           └──────────────────────┘               └─────────┬────────────┘
        │                                    │                                      │ thin API
        ▼                                    ▼                                      ▼
   data/raw/<src>/current/            data/processed/                  ┌──────────────────────────┐
   data/manifest.json                  ├── normalized/<src>/           │  backend/  (Slice 4)     │
                                       │   ├── <type>.parquet          │   FastAPI + Postgres +   │
                                       │   ├── <type>/*.parquet        │   S3 + Claude API        │
                                       │   ├── raw.parquet | raw/      │   username/password auth │
                                       │   └── quality_report.json     │   tenant-shaped Day 1    │
                                       ├── composite/<fips>/           └──────────┬───────────────┘
                                       │   ├── catalog.json                       │
                                       │   ├── summary.json                       ▼
                                       │   ├── parcels.parquet (+ geojson)   Postgres + S3
                                       │   ├── towers.parquet (+ geojson)    (uploaded lease PDFs,
                                       │   ├── solar_facilities.parquet …   lead state, activity log,
                                       │   ├── distress_overlays.parquet …  scoring profiles, lease
                                       │   ├── county_scores.parquet        comps, owner_cluster_override)
                                       │   └── views/<name>.parquet (+ geojson)
                                       └── preprocess_manifest.json
```

Each subsystem is independently runnable: the puller doesn't need preprocess installed; preprocess doesn't need the map app; the map app reads static files written by preprocess and (in Slice 4) hits the backend over a thin API for write-layer state.

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

**Spatial (data pipeline):** `tower`, `parcel`, `distress_overlay`, `solar_facility`, `billboard`, `address_point`.

**Tabular (data pipeline):** `county_score`, `license`, `location`, `entity`, `transfer`, `lease`, `distributed_pv`, `aggregation`, `model_prediction`.

**Backend tables (Slice 4 — new):** `lead`, `lease` (product-side, with PDFs + extracted fields), `activity`, `owner_cluster_override`, `lease_comp`, `scoring_profile`, `tenant`, `user`, `user_tenant`. Schema details in §5.1.

> NB: there are **two** entities called `lease` in the codebase — the *data-pipeline* tabular canonical type (placeholder for normalized recorded-lease data, deferred to Phase 2) and the *backend* `lease` table (Slice 4, holds uploaded PDF references + LLM-extracted fields per (tower × carrier)). They will reconcile in Phase 2 when recorded-lease automation lands.

Every record (data-pipeline side) gets system columns: `_source`, `_processed_at`, `_schema_version`, `_tenant_id`, `_quality_score`, `valid_from`, `valid_to`.

Every backend row has `tenant_id` (Day 1 = `1`; multi-tenant from row-add — [ADR-055](./adr/0055-hosted-private-backend.md)).

### 3.3 Full-fidelity raw preservation

Every Normalizer writes both:

- a **raw** copy — every column from the source, untouched (renamed
  only to legal Parquet names if necessary), all rows, no filtering.
- a **canonical** copy — the canonical-schema view derived from the
  raw. May filter, rename, retype, derive columns.

Future questions ("what's in the source's hidden `_dor_remarks` field?")
get answered without re-downloading.

**On-disk layout depends on source size.** Simple single-layer
sources write `raw.parquet` + `<canonical_type>.parquet` at the
source root. Large multi-layer parcel sources (the state-parcel
normalizer — AR, MT, FL FDOR) **stream per-county**: the normalizer
processes one county-layer at a time and writes one parquet per
county under `normalized/<source>/<type>/<county>.parquet`, with the
raw copy under `normalized/<source>/raw/<county>.parquet` (ADR-050).
This keeps peak memory bounded to a single county — Florida's
67-county / ~28 GB FDOR set would otherwise need ~50 GB of RAM.

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

1. Loads every canonical layer from `normalized/<source>/` — either a
   single `<type>.parquet` or, for per-county sources, every parquet
   under `<type>/` — and filters to the state (via the `state_fips`
   column or a bbox fallback).
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

The **Composer** writes every spatial output as both formats; for
layers ≥ 100K rows only the simplified-geometry GeoJSON is written.
Parquet is canonical for analytics; GeoJSON feeds the map app's
catalog layers (its parcel base layer is PMTiles, built from the
Parquet). The **normalize** stage writes GeoParquet only (ADR-050) — the
redundant normalize-stage GeoJSON was dropped, which made AR's
normalize both faster and smaller.

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

A Svelte 5 + Vite + MapLibre GL JS single-page app. Catalog-driven: it
binds to `composite/index.json` + per-state `catalog.json`, so any
state that composes appears with no app changes. Full detail — stack,
tile pipeline, filter engine, file layout — is in
[../app/ARCHITECTURE.md](../app/ARCHITECTURE.md).

### 4.1 What it does

- **State selector** from `composite/index.json` (one read, no per-FIPS
  probing).
- **Parcel base layer** — PMTiles vector tiles (all 2.1 M AR / 920 K MT
  parcels), read over HTTP Range.
- **County distress choropleth** at low zoom; parcels fade in and take
  over at z ≥ 10.
- **Catalog layers + views** — towers, distress overlays, solar
  facilities, the interestingness views — GeoJSON layers with toggles
  and a legend.
- **DuckDB-WASM filter & search** — filter 2 M+ parcels by owner type,
  distress, hosted infrastructure, value, acreage, county, etc.;
  owner-name + APN search; full-row detail panel; shareable URL
  deep links.

### 4.2 Build inputs

The app's data is produced by the preprocess pipeline and discovered by
convention: `composite/index.json` (the index writer), per-state
`parcels.pmtiles` (`tiles.py`), `parcels_attr.parquet` + `facets.json`
(`facets.py`), `county_boundaries.geojson` (`county_boundaries.py`) —
all behind `preprocess.py --app-assets` / `--tiles`. The app is served
against the range-capable `scripts/serve.py`; `python -m http.server`
cannot serve it (PMTiles + DuckDB-WASM need HTTP 206).

The v1 Leaflet prototype is retired (preserved in git history). The realized design is locked in [ADR-030](./adr/0030-map-app-v2-stack.md).

---

## 5. Subsystem 4 — The backend (Slice 4 — in design, `backend/`)

> **NOTE:** This section is the original Slice 4 **design**. A substantial part of it is now **implemented** in `backend/` (the lead write-layer + username/password auth + owner merge/split — Slices #47–#53 + PRD #75); lease upload, LLM extraction, and S3 storage remain unbuilt. Where the implemented backend differs from the sketch below, [`backend/README.md`](../backend/README.md) is authoritative for what's on disk.

A small FastAPI + Postgres + S3-compatible + Claude-API service that stands up in Phase 1 Slice 4 (D + E). Holds the **write-layer features** the static map app can't: lead state, uploaded lease PDFs, LLM-extracted lease fields, activity log, per-user scoring profiles, manual owner-cluster merge/split overrides. Lives **alongside** the static map app — the map app reads parquet + PMTiles via HTTP range requests for analytical layers, and hits the backend over a thin API for the write-layer state.

Locked architectural decisions:
- **Hosted-private** — single small VM (Fly.io / Render / Hetzner class); ~$30-100/mo Phase 1 ([ADR-055](./adr/0055-hosted-private-backend.md), supersedes ADR-006 for write features).
- **Tenant-shaped schema from Day 1** — every table has a `tenant_id` column, always `1` for now. Adding a second tenant (intern / advisor / second cofounder / paid Phase-3 customer) is a row-add not a refactor.
- **Username/password auth over a credentials file** — `backend/users.txt` (`username:hash:team` lines, PBKDF2 hashes, managed via `python -m app.users`); **teams are tenants**; identity-only HS256 session JWTs with the file authoritative on every request. Replaced the original magic-link design and the interim `APP_USERS` env var ([ADR-062](./adr/0062-username-password-replaces-magic-link.md) / [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md)).
- **S3-compatible** object store for lease PDFs (Backblaze B2 / Cloudflare R2 / AWS S3) — encrypted at rest, signed download URLs only.
- **Postgres** — managed in prod; `testcontainers-postgres` in CI for real-Postgres testing (no SQLite-stub drift).
- **Claude API** — Sonnet 4.6 default + Opus 4.7 retry for lease extraction; prompt caching on ([ADR-059](./adr/0059-llm-lease-extraction.md)).

### 5.1 Tables (Slice 4 baseline)

```
tenant(id, name, created_at)
user(id, email, …)
user_tenant(user_id, tenant_id, role)

lead(tenant_id, owner_cluster_id, state, priority_score,
     latest_note, owner_user_id, updated_at)
        # state ∈ {new, flagged, contacted, talking,
        #          won, lost, passed, re_engage_later}

lease(tenant_id, parcel_id, tower_asr_id, carrier_callsign,
      state, pdf_object_key, extracted_fields_json,
      extraction_confidence_json, verified_at,
      monthly_rent_cents, escalation_pct, expiry_date,
      amendment_count, parties_text)
        # state ∈ {unknown, pending_upload, uploaded,
        #          extracted, verified, superseded}

activity(tenant_id, entity_type, entity_id, timestamp,
         user_id, action, content_md)

owner_cluster_override(tenant_id, source_cluster_id, target_cluster_id)
  # raw cluster IDs stay in parquet; backend computes
  # display_cluster_id = coalesce(override_target, raw_cluster_id)

lease_comp(state, county, asset_type, source, year,
           rent_mean, rent_p25, rent_p75, sample_size)
  # bootstrap rows from Steel-in-the-Air free tier;
  # augment rows from extracted-lease rent over time

scoring_profile(tenant_id, user_id, name, weights_json, …)
```

### 5.2 Two state machines

**Lead state** (on `owner_cluster_id`, tracks outreach lifecycle):

```
new → flagged → contacted → talking → {won | lost | passed}
                                  ↓
                          re_engage_later (timed; auto-returns to flagged)
```

**Lease state** (on `(parcel_id, tower_asr_id, carrier_callsign)`):

```
unknown → pending_upload → uploaded → extracted → verified
                                              ↓
                                          superseded (when amendment lands)
```

### 5.3 Where the backend touches the data pipeline

The backend **reads** static composite outputs over HTTP (it doesn't import the preprocess package directly). Specifically:
- `composite/<fips>/parcels.parquet` — for resolving `owner_cluster_id → parcel_id` list during lead-detail render.
- `composite/<fips>/views/<name>.parquet` — for view-driven triage queries.
- `composite/index.json` + per-state `catalog.json` — for what's available.

The backend **writes nothing** to `data/processed/` — it owns its own Postgres + S3 universe. The boundary stays clean: re-running the pipeline never collides with backend state.

### 5.4 LLM extraction loop

Per [ADR-059](./adr/0059-llm-lease-extraction.md):

1. Co-founder uploads a lease PDF → backend stores in S3, marks `lease.state = uploaded`.
2. Extraction worker reads PDF → calls Claude (Sonnet 4.6 first; Opus 4.7 retry if eval-flagged) with the lease's expected-fields schema.
3. Model returns `(value, page_number, verbatim_quote_from_source)` per field + self-rated confidence for inferred fields → backend stores in `extracted_fields_json` + denormalises common fields onto `lease` row, marks `lease.state = extracted`.
4. Co-founder reviews in lead-detail panel, optionally flips per-field confidence to `verified` → backend marks `lease.state = verified`, appends to `activity`.
5. Eval harness (gold-set runner, [TESTING.md §11.3](./TESTING.md)) re-runs accuracy whenever extraction code or prompts change. PR blocks if any field accuracy drops below 85%.

### 5.5 Auth + multi-tenancy

- Username/password login (`POST /api/auth/login`) → backend verifies against the credentials file `backend/users.txt` (PBKDF2 hashes) → mints an **identity-only** HS256 session JWT ([ADR-062](./adr/0062-username-password-replaces-magic-link.md) / [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md)).
- Every API route re-authorizes the session's username against the credentials file (mtime-cached) and resolves their *current* team → `tenant_id`; teams ARE tenants. Removing a user or changing their team applies on their next request. Multi-tenancy isolation tests gate every PR (see [TESTING.md §11.2](./TESTING.md)).

### 5.6 What's not in Slice 4

- **Self-serve refresh from the product** — Phase 2. The puller stays a dev-side desktop app for Phase 1.
- **Mass email + response tracking** — Phase 2. Requires email infra (Postmark / SES), webhook handling, CAN-SPAM compliance.
- **Multi-tenant traffic** — schema-ready, but only 1 tenant in Phase 1. Hosted-multi-tenant deployment is Phase 3.

---

## 6. Shared on-disk layout

```
data/
├── raw/<source_id>/current/         Latest raw per source
├── manifest.json                    Fetch manifest (puller-owned)
├── fetch.log                        JSONL event log (puller-owned)
└── processed/
    ├── normalized/<source>/         Canonical-schema GeoParquet + raw copy
    │   ├── <canonical_type>.parquet         (simple sources)
    │   ├── <canonical_type>/*.parquet       (per-county, large sources)
    │   ├── raw.parquet  OR  raw/*.parquet
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

## 7. Catalog format (the map-app contract)

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

The map app reads `composite/index.json` for the state list and each
state's `catalog.json` to discover its layers + views — adding a View
at preprocess time produces a new toggle in the UI with zero JS changes.

---

## 8. Code conventions

- **Headless `fetch/`.** No PySide6 imports inside `scripts/fetch/`.
  Qt lives only in `app_puller/`.
- **Atomic writes everywhere.** Download to `.partial`, rename.
  Manifest writes go through `Manifest.save()` (temp + rename).
- **Preprocess outputs EPSG:4326.** Every spatial output reprojected
  to WGS84 lat/lon.
- **Sparse comments.** Comments where the *why* is non-obvious; not
  where the code self-documents.
- **No new normalize-time filtering.** Per ADR (full-fidelity raw preservation): keep all rows; add status / validity columns; let Joins and Views filter.
- **Backend (Slice 4) — `tenant_id` everywhere.** Every table has it; every route filters by it; multi-tenancy isolation tests gate PRs.
- **Backend — no direct writes to `data/processed/`.** Backend owns Postgres + S3; pipeline owns `data/processed/`. Boundary stays clean.

---

## 9. Where to look

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
| Map app architecture? | [../app/ARCHITECTURE.md](../app/ARCHITECTURE.md) |
| Test strategy? | [TESTING.md](./TESTING.md) |
| Puller UX design? | [PULLER_UX.md](./PULLER_UX.md) |
