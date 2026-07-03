# ARCHITECTURE — How the system fits together

**Last updated:** 2026-06-26
**Audience:** engineers (human or AI) who need to understand or extend the code without reading every file.

This doc describes what's *implemented today*. The backend has shipped and is **live in
production** (Fly app `morphy-consulting`); only lease-doc upload + LLM extraction (the rest
of D+E, [ADR-059](./adr/0059-llm-lease-extraction.md)) remain unbuilt. Future-state designs
live in [ROADMAP.md](./ROADMAP.md). Design decisions are locked under [docs/adr/](./adr/) —
[DECISIONS.md](./DECISIONS.md) is the cross-doc index.

---

## 1. System overview

**Four subsystems today** — the data puller, the preprocess pipeline, the map app, and the
live write-layer backend (lead state, tasks, auth). The map app + the standalone
**data-audit catalog** (`audit-site/`, served at `/audit/`) are static SPAs; the backend
serves write-layer state + the **Ask Claude** SSE stream and edge-gates `/data/processed/*`.

```
┌──────────────────────┐    raw/   ┌──────────────────────┐  normalized/  ┌──────────────────────┐
│  scripts/data_tui/   │──────────▶│  scripts/preprocess/ │──────────────▶│  app/  (map browser) │
│   Textual TUI        │           │   Normalize → Join → │  composite/   │   Svelte + MapLibre  │
│   pull → preprocess  │           │   View → Compose     │               │   PMTiles + DuckDB   │
│   → verify → deploy  │           │   (DuckDB engine)    │               │                      │
└──────────────────────┘           └──────────────────────┘               └─────────┬────────────┘
        │                                    │                                      │ thin API (cookie auth)
        ▼                                    ▼                                      ▼
   data/raw/<src>/current/            data/processed/                  ┌──────────────────────────┐
   data/manifest.json                  ├── normalized/<src>/           │  backend/  (live in prod) │
                                       │   ├── <type>.parquet          │   FastAPI + SQLAlchemy    │
                                       │   ├── <type>/*.parquet        │   SQLite + Litestream→R2  │
                                       │   ├── raw.parquet | raw/      │   username/password auth  │
                                       │   └── quality_report.json     │   tenant-scoped (teams)   │
                                       ├── composite/<fips>/           └──────────┬───────────────┘
                                       │   ├── catalog.json                       │
                                       │   ├── summary.json                       ▼
                                       │   ├── parcels.parquet (+ geojson)   SQLite-on-volume + R2
                                       │   ├── towers.parquet (+ geojson)    (lead/contact_attempt/task/
                                       │   ├── solar_facilities.parquet …   owner_cluster_override/
                                       │   ├── distress_overlays.parquet …  scoring_preset/ask_log/…;
                                       │   ├── county_scores.parquet        lease-PDF storage planned)
                                       │   └── views/<name>.parquet (+ geojson)
                                       └── preprocess_manifest.json
```

Each subsystem is independently runnable: the puller doesn't need preprocess installed;
preprocess doesn't need the map app; the map app reads static files written by preprocess and
hits the backend over a thin API (httpOnly-cookie auth) for write-layer state.

---

## 2. Subsystem 1 — The data puller (`scripts/data_tui/`, `scripts/fetch/`)

A Textual terminal app (PRD #233; it replaced the retired PySide6 desktop puller in
#240) that fetches the registered data sources into `data/raw/<source_id>/current/`
— 16 active sources, plus deferred ones split out via the `_ACTIVE` / `_DEFERRED`
registry blocks (ADR-045) — then drives preprocess, composite verify, and the
confirm-gated data deploy from the same screen.

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

`scripts/data_tui/app.py` shows a category-grouped table of every
registered source with freshness badge, size, version, and an attention
panel ranking what needs action. Key bindings:

- **`c`** — check for updates: parallel sweep across all sources.
- **`p` / `P`** — pull one source / pull all stale (background worker,
  byte/speed progress, resume, desktop notification on completion).
- **`w` / `i`** — guided walkthrough + install-from-file for the manual
  path (and as fallback when an auto endpoint rots).
- **`r`** — preprocess, preseeded with the states affected by what was
  just pulled (pure planner in `data_tui/planner.py`).
- **`v`** — verify + deploy: composite diff vs the last deploy receipt,
  then the confirm-gated `deploy.sh data` flow with smoke checks
  (`data_tui/verify.py`, `data_tui/deploy.py`).
- **`d`** — diagnose a failure with the LLM (`scripts/diagnose.py`).

### 2.6 Headless reuse

The `scripts/fetch/` package is intentionally UI-free. The TUI is just
the shell on top — a CLI could call `fetch.puller.fetch_one()` directly
without importing Textual.

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

**Backend tables (shipped, 12):** `lead`, `contact_attempt`, `owner_cluster_override`, `antenna_override`, `credential`, `tenant`, `task`, `tenant_setting`, `user_setting`, `scoring_preset`, `ask_log`, `app_user`. The lease-PDF + extracted-fields tables are still unbuilt (rest of D+E). [`backend/README.md`](../backend/README.md) is authoritative for the live schema.

> NB: the *data-pipeline* `lease` canonical type (placeholder for normalized recorded-lease data, deferred to Phase 2) is distinct from the planned *backend* lease-document table (rest of D+E — uploaded PDF references + LLM-extracted fields per (tower × carrier), not yet on disk). They reconcile in Phase 2 when recorded-lease automation lands.

Every record (data-pipeline side) gets system columns: `_source`, `_processed_at`, `_schema_version`, `_tenant_id`, `_quality_score`, `valid_from`, `valid_to`.

Every backend row has `tenant_id`, and every route filters by it. **Teams ARE tenants** — `tenant_id` is resolved from the user's current team on every request ([ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md)); there is no `tenant_id = 1` stub. A second team is a row-add, not a refactor ([ADR-055](./adr/0055-hosted-private-backend.md)).

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

The compose stage runs **chunked** (per-county streaming, ADR-051 — the only compose path)
and uses **DuckDB as the heavy-lift engine** (PRD #135; `scripts/preprocess/duck.py` owns the
connections, equivalence pinned by `tests/test_duckdb_equivalence.py`), which keeps peak
memory bounded so large states (FL's 11.4M parcels) fit on a 16 GB dev machine.

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

## 5. Subsystem 4 — The backend (`backend/`, live in production)

> **NOTE:** The backend is **shipped and live in production** (lead write-layer + Tasks +
> username/password auth + owner merge/split + per-user settings + scoring presets + the Ask
> Claude SSE stream). Only lease-PDF upload + LLM extraction remain unbuilt (rest of D+E). The
> sketch below is the original design; where it differs from disk,
> [`backend/README.md`](../backend/README.md) is authoritative for the live 12-table schema +
> routes.

A FastAPI + SQLAlchemy service, **live in production**, that holds the **write-layer features** the static map app can't: lead + task state, contact attempts, activity log, per-user scoring presets/settings, manual owner-cluster merge/split overrides (lease-PDF upload + LLM extraction are the next unbuilt slice). Lives **alongside** the static map app — the map app reads parquet + PMTiles via HTTP range requests for analytical layers, and hits the backend over a thin API for the write-layer state. (Auth + schema + migration mechanics are canonical in [`backend/README.md`](../backend/README.md).)

Locked architectural decisions:
- **Hosted-private** — single Fly.io always-on machine, SQLite-on-volume + Litestream→R2 backups, Cloudflare front; ~$5–8/mo ([ADR-055](./adr/0055-hosted-private-backend.md) → [ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md); supersedes ADR-006 for write features).
- **Tenant-shaped schema from Day 1** — every table has `tenant_id`; **teams are tenants** (registration order). Adding a tenant is a row-add, not a refactor.
- **Username/password auth, per-request authority** — credentials live in the app DB's `credential` table (managed via `python -m app.users`); identity-only HS256 session JWT in an httpOnly cookie, the credential table authoritative on every request (API routes *and* the edge-gated `/data/processed/*`) ([ADR-062](./adr/0062-username-password-replaces-magic-link.md) / [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md) / [ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)).
- **SQLite-on-volume in prod** (Litestream→R2), DB-agnostic ORM (`DATABASE_URL` → Postgres when scale demands); `testcontainers-postgres` opt-in in CI. Schema changes ship as Alembic revisions (PRD #134).
- **S3-compatible** object store (R2) for lease PDFs — planned with D+E; encrypted at rest, signed download URLs only.
- **Claude API** for lease extraction — planned with D+E ([ADR-059](./adr/0059-llm-lease-extraction.md)).

### 5.1 Tables (original design sketch — see backend/README.md for the live schema)

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

The backend **writes nothing** to `data/processed/` — it owns its own store (SQLite-on-volume + R2 object storage). The boundary stays clean: re-running the pipeline never collides with backend state.

### 5.4 LLM extraction loop

Per [ADR-059](./adr/0059-llm-lease-extraction.md):

1. Co-founder uploads a lease PDF → backend stores in S3, marks `lease.state = uploaded`.
2. Extraction worker reads PDF → calls Claude (Sonnet 4.6 first; Opus 4.7 retry if eval-flagged) with the lease's expected-fields schema.
3. Model returns `(value, page_number, verbatim_quote_from_source)` per field + self-rated confidence for inferred fields → backend stores in `extracted_fields_json` + denormalises common fields onto `lease` row, marks `lease.state = extracted`.
4. Co-founder reviews in lead-detail panel, optionally flips per-field confidence to `verified` → backend marks `lease.state = verified`, appends to `activity`.
5. Eval harness (gold-set runner, [TESTING.md §11.3](./TESTING.md)) re-runs accuracy whenever extraction code or prompts change. PR blocks if any field accuracy drops below 85%.

### 5.5 Auth + multi-tenancy

- Username/password login (`POST /api/auth/login`) → backend verifies against the app DB's `credential` table (PBKDF2 hashes) → mints an **identity-only** HS256 session JWT, set in an httpOnly cookie ([ADR-062](./adr/0062-username-password-replaces-magic-link.md) / [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md) / [ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)).
- Every request re-authorizes the session's username against the `credential` table and resolves their *current* team → `tenant_id`; teams ARE tenants. Removing a user or changing their team applies on their next request — including the edge-gated `/data/processed/*`. Multi-tenancy isolation tests gate every PR (see [TESTING.md §11.2](./TESTING.md)). Full mechanics: [`backend/README.md`](../backend/README.md).

### 5.6 What's not in the backend yet

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

- **Headless `fetch/`.** No UI imports inside `scripts/fetch/`.
  Textual lives only in `scripts/data_tui/`.
- **Atomic writes everywhere.** Download to `.partial`, rename.
  Manifest writes go through `Manifest.save()` (temp + rename).
- **Preprocess outputs EPSG:4326.** Every spatial output reprojected
  to WGS84 lat/lon.
- **Sparse comments.** Comments where the *why* is non-obvious; not
  where the code self-documents.
- **No new normalize-time filtering.** Per ADR (full-fidelity raw preservation): keep all rows; add status / validity columns; let Joins and Views filter.
- **Backend — `tenant_id` everywhere.** Every table has it; every route filters by it; multi-tenancy isolation tests gate PRs.
- **Backend — no direct writes to `data/processed/`.** Backend owns its store (SQLite + R2); pipeline owns `data/processed/`. Boundary stays clean.

---

## 9. Where to look

| Question | File |
|---|---|
| What is the project? | [PROJECT_BRIEF.md](../PROJECT_BRIEF.md) |
| What's in scope right now? | [SCOPE.md](./SCOPE.md) |
| What does success look like? | [SCOPE.md](./SCOPE.md) |
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
