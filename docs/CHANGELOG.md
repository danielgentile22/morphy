# CHANGELOG

**Last updated:** 2026-05-25

History of meaningful changes to the project. Newest at the top.
Format follows [Keep a Changelog](https://keepachangelog.com/)
loosely; semver isn't enforced because this isn't a released package.

Changes are grouped under section headers (`Added` / `Changed` /
`Fixed` / `Removed` / `Deprecated` / `Documented`).

---

## 2026-05-25 — Phase 1 product pivot

The project reframed from "v1 pitch-quality demo" to "Phase 1 of a co-founder-facing product." The audience changed (investor walkthrough → co-founder daily user); several previously-deferred feature areas flipped to in-scope; five legacy ADRs were superseded, revised, or narrowed. Result of a `/grill-with-docs` session (16 substantive grills + wrap-up). Full record: `docs/grill-2026-05-25-summary.md`.

### Documented

- **7 new ADRs in `docs/adr/`:**
  - ADR-053 — Product phase shift (pitch → product)
  - ADR-054 — Phase 1 freestanding / Phase 2 rooftops
  - ADR-055 — Hosted-private backend (supersedes ADR-006)
  - ADR-056 — Lead = owner-cluster (drives ADR-024 follow-up)
  - ADR-057 — Budget posture reframed (revises ADR-010 + ADR-041)
  - ADR-058 — Tunable + transparent scoring
  - ADR-059 — LLM extraction approach for leases
- **6 doc rewrites:** SCOPE.md, GOALS.md, ROADMAP.md, STATUS.md (Phase 1 framing); DECISIONS.md (pointer block + status lines on superseded/revised ADRs); CLAUDE.md (orientation header + slice plan in §3).
- **`docs/grill-2026-05-25-summary.md`** — comprehensive session memo: ADR map, slice plan, below-the-ADR-bar decisions (comparables data model, lead/lease state machines, ULS join strategy, testing additions, owner-cluster strengthening, freshness UX), Q&A trail, open items.
- **`CONTEXT.md`** (repo root) updated with canonical glossary: Vendor / Carrier / Registrant / Freestanding tower / Rooftop installation / Triage.
- **GLOSSARY.md, LIMITATIONS.md, SECURITY.md, DEPLOYMENT.md, DATA_SOURCES.md, TESTING.md, ARCHITECTURE.md, DATA_FRESHNESS.md, MAP_APP_REHAUL.md, PULLER_UX.md** all updated to reflect Phase 1 framing.

### Changed

- **ADR-006** (static-site, no backend) — superseded by ADR-055 for write-layer features. Read-only analytical layers stay static.
- **ADR-010** (free-only budget) — reframed by ADR-057 from "permanent stance" to "current budget posture." Paid unlocks expected Phase 2+.
- **ADR-013** (FCC ULS deferred) — partially reversed. Cellular (Part 22) + PCS (Part 24) + AWS / 700 MHz (Part 27) flip to in-scope for Phase 1 Slice A. Microwave, Ownership, Transfers, Leasing still deferred.
- **ADR-014** (Billboards deferred) — partially reversed. Billboards run as **parcel enrichment** (`has_billboard`, `billboard_count`) in Phase 1 Slice C. Billboards-as-primary asset class still deferred to Phase 3.
- **ADR-024** (Owner clustering = SHA1) — follow-up locked in ADR-056. Slice 4 layers stronger conservative normalization (suffix stripping, name-token sort, trust/estate normalization, USPS address standardization) + a manual merge/split UI before the SHA1 hashing. Phonetic match excluded.
- **ADR-041** (No LLC unmasking) — narrowed by ADR-057 to paid skip-trace + shell-piercing only. Free public-records officer disclosure (SoS, UCC-1) is in scope for Slice 4 lead-detail panel.

### Added — Phase 1 slice plan (locked, untimed)

1. **F** — Finish FL + NC composes (chunked compose ADR-051 + NC re-fetch)
2. **A** — FCC ULS carrier identification (Cellular + PCS + AWS / 700 MHz)
3. **C** — Asset enrichment (billboards + solar on parcel) + tunable scoring UI
4. **D + E** — Lease doc upload + LLM extraction + triage state / write layer / CSV exports (**backend stands up here**)
5. **B** — Vendor (tower-co) inference

Per-slice quantitative "shipped" gates in GOALS.md §3. Overall outcome bar: co-founder uses the product as his primary daily triage tool for 4 consecutive weeks.

---

## Unreleased — production-readiness push (legacy framing — superseded 2026-05-25)

As of 2026-05-21, Sections 1–3 are done, Section 4 complete for AR/MT,
and Section 5 (preprocess code hygiene) is complete. A full AR + MT
data-quality remediation followed — both states pass a 9-check audit
with **zero warnings**. FL/NC compose remains blocked pending a
chunked-compose refactor (ADR-051). See [STATUS.md](./STATUS.md) for
the current snapshot.

### Added (Section 8 — map app rehaul · 2026-05-21)

- **New map app at `app/`** — Svelte 5 + Vite 8 + TypeScript + MapLibre
  GL JS 5, replacing the v1 Leaflet prototype (retired to
  `app_legacy_v1/`). Catalog-driven: it binds to `composite/index.json`
  + per-state `catalog.json`, so any state that composes appears with
  zero app changes. See [app/ARCHITECTURE.md](../app/ARCHITECTURE.md).
- **PMTiles parcel base layer** — all 2.1 M AR / 920 K MT parcels render
  as vector tiles, read over HTTP Range. County choropleth (ARC distress
  tier) at low zoom; parcels take over at z ≥ 10.
- **DuckDB-WASM filter & search engine** — filter 2 M+ parcels by owner,
  distress, infrastructure, value, etc. (3-filter query < 500 ms);
  owner-name + APN search; full-row detail panel. URL deep-linking.
- **Preprocess app-asset scripts** — `tiles.py` (parcels.pmtiles),
  `facets.py` (slim `parcels_attr.parquet` + `facets.json`),
  `county_boundaries.py`, and the `composite/index.json` writer;
  `--app-assets` / `--tiles` flags on `scripts/preprocess.py`.
- **`scripts/serve.py`** — a range-capable static server. The app's
  PMTiles + DuckDB-WASM range reads need HTTP 206; `python -m
  http.server` does not send it.
- Test suites: pytest for the app-asset scripts; Vitest (unit) +
  Playwright (E2E, Chromium + WebKit) for the app.

### Fixed (AR + MT data-quality remediation — 2026-05-21)

- **Tower geometry: ~25% → 100%.** The composite `towers` layer merges
  FCC ASR + FAA OEAAA. The FAA normalizer's fixed-width column offsets
  in `faa_oeaaa.py` were misaligned, so every FAA obstacle's lat/lon
  failed to parse and the row landed with null geometry (~75% of AR
  towers, ~69% of MT). Corrected `_FW_FIELDS` — verified all 636k FAA
  rows now parse to a valid coordinate. FCC ASR was separately
  re-normalized off a stale pre-baseline output. Tower→parcel join
  rate rose to 88.6% (AR) / 99.2% (MT) from ~23–31%.
- **Distress overlays recovered.** HUD Opportunity Zones, HUD Qualified
  Census Tracts, and USDA persistent-poverty counties had never been
  pulled — `in_oz` / `in_qct` / `persistent_poverty` were uniformly
  `False` placeholders. Pulled all three; fixed `hud_overlays.py` to
  write `distress_overlays.parquet` (the basename the composer's
  `_load_state_data` looks up — it had been writing
  `opportunity_zones.parquet` / `qualified_census_tracts.parquet`,
  which were silently never loaded) plus a GEOID-derived state/county
  fallback. `parcel_to_distress` + `tower_to_distress` joins now run —
  **11 joins** total (was 9).
- **`parcels.geojson` no longer multi-GB** — added `NO_GEOJSON_THRESHOLD`
  (ADR-052): layers ≥ 250K rows write Parquet only. AR's 3.9 GB and
  MT's 1.8 GB `parcels.geojson` are gone (~5.7 GB reclaimed).
- **`owner_kind` government classification rewritten.** Federal, state,
  county, tribal, and public-authority owners (BLM, USDA/USDI, Forest
  Service, state highway commissions, housing/airport/port authorities,
  "USA IN TRUST", Indian reservations, county governments, Montana's
  consolidated city-counties) were mis-tagged `individual`/`trust`. The
  expanded `cluster.py` patterns match a punctuation-normalised name so
  abbreviations are caught; the outreach views are now clean of
  government at the top.
- **AR `unknown` owner rate 50.8% → 2.1%** (MT 35.4% → 4.9%) — the
  classifier had rejected any comma/ampersand-formatted name, but AR
  assessor data is overwhelmingly "SURNAME, FIRST" and "X & Y" joint
  owners. Added separator-aware person-name detection.
- **Federal owner-cluster fragmentation** — "USA" / "U S" / "U S A" /
  "US US" now collapse to one canonical cluster key.
- **`towers.geojson` carried null-geometry features** — `write_geojson`
  drops null/empty geometry rows (Parquet keeps every row).
- `catalog.json` now carries `schema_version: 3`; `summary.json`
  records `joins_skipped`; catalog `geojson_path` is existence-gated;
  `--rebuild-manifest` reads `summary.json` so the rebuilt manifest
  carries the join/source lists.

### Data (AR + MT remediation — 2026-05-21)

- **AR** re-composed: 2,116,976 parcels, 15,846 towers, 246
  distress-overlay tracts, 150 county scores, 11 joins, 8 views, 0
  warnings.
- **MT** re-composed: 920,111 parcels, 4,728 towers, 76
  distress-overlay tracts, 112 county scores, 11 joins, 8 views, 0
  warnings.
- Tower *geometry* coverage went ~25% → 100% (the FAA fix); tower
  *counts* are unchanged — FCC ASR registrations + FAA obstacles
  combined, as before.
- Distress now populated: AR 215,261 OZ / 309,318 QCT / 208,278
  persistent-poverty parcels; MT 78,494 / 104,866 / 53,468.
- `interestingness_score` is no longer capped at 0.700 — the distress
  component is live (AR max 0.900, MT 0.950).
- Sources newly feeding the AR/MT composites: `hud_oz`, `hud_qct`,
  `usda_persistent_poverty`; `faa_oeaaa` + `fcc_asr` re-normalized.

### Removed (data cleanup — 2026-05-20)

- **`data/processed/normalized/fdor_nal/`** (10.2 GB) — FL normalized
  parcels deleted to recover disk space. Raw FDOR data at
  `data/raw/fdor_nal/current/` is untouched. Re-run
  `python scripts/preprocess.py --state 12` once chunked compose
  is built (ADR-051).
- **`data/processed/composite/12/`** (70 MB) — FL composite deleted.
  Same precondition as above.
- **`data/raw/nc_onemap_parcels/`** (8.3 GB) — NC raw MapServer pages
  deleted (was stalled at 1,106/1,186 pages on a server 504). Needs
  a full re-fetch when the NC OneMap endpoint is confirmed stable.
- **`data/raw/NC/`** (958 MB) — legacy NC raw directory (Graham County
  shapefiles + old FCC docs). FCC content was a duplicate of
  `data/raw/fcc_asr/current/`; Graham County parcels were v0 pilot
  data superseded by nc_onemap_parcels.
- **`data/_stale_backup/`** (2.3 GB) — old FL FGDL DSL normalized
  parcels + old composite/12; superseded by fdor_nal (ADR-046).

`preprocess_manifest.json` rebuilt via `--rebuild-manifest`; now
shows 9 normalized sources + 3 composed states (AR/IN/MT).

### Fixed (Section 5 — 2026-05-20)

- **Latent bug:** `scripts/preprocess/registry.py` was empty — no
  normalizer / join / view modules were imported, so every registry
  was empty and `preprocess.py` was a silent no-op. Populated it with
  all 11 normalizer, 12 join, and 8 view module imports.
- **MT field map was wrong.** `mt_cadastral_parcels` had incorrect
  column names, and a silent "fall back to all layers" path
  concatenated all 12 Montana shapefiles (including PLSS points and
  water) into one garbage 6.5M-row output with 0 owner names.
  Corrected the field map to the real schema (`OwnerName`,
  `PARCELID`, `GISAcres`, `TotalValue`, …) and replaced the silent
  fallback with a loud `RuntimeError`. MT now normalizes to 920,111
  rows, 96% owner names, all 56 counties resolved to FIPS.

### Added (Section 5 — 2026-05-20)

- FDOR NAL parcel normalizer (`fdor_nal` in `state_parcels.py`):
  field map verified against the real 2025 PAR `.dbf` schema
  (`OWN_NAME`, `OWN_ADDR1`, `JV`, `LND_VAL`, `DOR_UC`, `ACT_YR_BLT`,
  county FIPS sliced from the `CENSUS_BK` GEOID).
- `safe_merge()` helper in `preprocess/base.py` — drops a
  Normalizer's placeholder columns before a Join merges the real
  values, preventing silent `_x` / `_y` collisions. Applied to all
  three `county_score_to_*` joins.
- `preprocess.py --source <id>` — re-normalize one source through the
  manifest without touching the others.
- `catalog.json` now carries `sources_used_versions` —
  `{source_id: raw_local_version}` lineage per state composite.
- `canon_county_fips()` now accepts census tract/block GEOIDs
  (slices positions 0-4) — needed for FDOR, whose only county
  identifier is `CENSUS_BK`.

### Changed (Section 5 — 2026-05-20)

- **Rewrote the parcel normalizer to stream per-county** (ADR-050).
  The old design read every layer of a multi-layer source, held them
  all in memory, and concatenated — which would need ~50 GB peak for
  Florida's 67-county / ~28 GB FDOR set. The normalizer now processes
  one county-layer at a time and writes a per-county parquet file
  under `normalized/<source>/parcels/<county>.parquet` (plus a raw
  copy under `raw/`). Peak memory is bounded to a single county.
- Normalize-stage GeoJSON output was dropped — only GeoParquet is
  written at the normalize stage now (the Composer still dual-writes
  GeoParquet + GeoJSON for the map app). This made AR's normalize
  *faster and smaller*: ~2m29s wall-clock, 1.3 GB output (down from
  the earlier dual-write).
- Vectorized the parcel-normalize mapping step (was a per-row
  `iterrows` loop — the documented hot path). Every canonical column
  is now a column-wise operation; the three regex-heavy scalar
  functions (`infer_owner_kind`, `normalize_owner_name`,
  `normalize_address`) run once per *distinct* value via a
  unique-lookup.

### Data (Section 4–5 — 2026-05-20)

- **AR** re-normalized + re-composed clean after the normalizer
  rewrite: 2,116,976 parcels, 9 joins, 8 views, 0 warnings.
- **MT** normalized + composed clean: 920,111 parcels, 9 joins, 8
  views, 0 warnings.
- **FL (`fdor_nal`)** re-normalized clean: all 67 counties,
  **11,184,113 parcels** (68 county parquet files, incl. the
  Miami-Dade condo supplement). The unclosed-ring geometry bug is
  fixed — `on_invalid="fix"` on the layer reads + an `is_file()` guard
  on the `.shp` glob; 2,976 rows (0.03%) dropped for unrepairable
  geometry. **FL compose is blocked** — ~19.5 GB peak RAM + ~16–20 GB
  output won't fit the 16 GB / near-full-disk dev machine. See
  [STATUS.md §4.1](./STATUS.md).
- **NC** fetch is ~93% done — **1,106 of 1,186** MapServer pages
  (~8.6 GB) fetched and valid; the fetch then stalled on a server-side
  HTTP 504 at deep offsets. Not yet normalized or composed. See
  [STATUS.md §4.2](./STATUS.md).

### Added (Section 2 — 2026-05-19)

- `.gitignore` + `.gitattributes` (data/ excluded; PII-safe by default).
- `pyproject.toml` — ruff + pytest + coverage config.
- `requirements-dev.txt` — ruff, pytest, pytest-cov, jsonschema.
- `.github/workflows/lint.yml` — ruff check + format check on every push.
- `.github/workflows/test.yml` — placeholder; activates when `tests/` exists.
- `.github/PULL_REQUEST_TEMPLATE.md` referencing TESTING + CHANGELOG rules.
- `CODEOWNERS`.
- Initial commit + GitHub repo at
  `https://github.com/danielgentile22/infra-lease-analytics` (private).
- CI: both `lint` and `test` jobs green on first push.

### Changed (Section 2 — 2026-05-19)

- Ruff baseline applied across the codebase: 62 files reformatted,
  281 lint auto-fixes (modern typing syntax, unused-import cleanup,
  import ordering).
- 4 small dead-code removals surfaced by `F841` (unused local
  variables in `main_window.py`, `preprocess_dialog.py`, `runner.py`,
  `verify_raw.py`).

### Documented (Section 1 — 2026-05-19)

- Created `docs/` directory + `docs/archive/` + `docs/pitch-assets/`.
- New docs: `SCOPE.md`, `GOALS.md`, `STATUS.md`, `ROADMAP.md`,
  `DECISIONS.md`, `GLOSSARY.md`, `ARCHITECTURE.md`,
  `DATA_FRESHNESS.md`, `LIMITATIONS.md` (expanded), `TESTING.md`,
  `DEPLOYMENT.md`, `SECURITY.md`, `PULLER_UX.md`, this `CHANGELOG.md`.
- Pending in this push: move existing root docs into `docs/`,
  split `PREPROCESSING_PLAN.md`, archive `scripts/_legacy/`, slim
  `README.md` + `CLAUDE.md`.

### Locked decisions captured in `docs/DECISIONS.md`

- ADR-010: Free-only budget for v1 pitch.
- ADR-011: Anchor states locked = AR + NC + MT + UT (+ FL stretch).
- ADR-012 through ADR-019: source-by-source decisions (defer / retire /
  drop / replace).
- ADR-020: `safe_merge` helper for joins with pre-initialized columns.
- ADR-021: `--source` flag for selective rebuild.
- ADR-022: `--rebuild-manifest` for disk-derived manifest sync.
- ADR-030: Map app v2 stack locked (MapLibre + PMTiles + DuckDB-WASM +
  Svelte).
- ADR-031: Map app rehaul deferred to post-pitch.
- ADR-040: Parcel-owner data treated as PII.
- ADR-042: Documentation moved to `docs/` subfolder.
- ADR-043: pytest now; Vitest + Playwright deferred to map app v2.
- ADR-044: CI on GitHub Actions.
- ADR-045: Registry split into `_ACTIVE` / `_DEFERRED` blocks.
- ADR-046 / ADR-047: FL FDOR NAL replaces FGDL DSL; coverage expanded
  to all 67 counties.
- ADR-048: NC OneMap auto-fetch via MapServer pagination.
- ADR-049: Utah dropped from anchor states (no owner data).
- ADR-050: Streaming per-county parcel normalize.
- ADR-051: Chunked compose for memory-bounded large states (approved;
  not yet implemented).

---

## 2026-05-18 — v3 framework end-to-end

### Added

- Per-state Composer with `--state` / `--compose-only` / `--list-states`
  CLI surface.
- 12 joins under `scripts/preprocess/joins/`.
- 8 views under `scripts/preprocess/views/`.
- Owner clustering (SHA1 of normalized name + address).
- Interestingness scoring (composite per-parcel 0–1 score).
- Geometry derivatives (centroid, bbox, simplified, H3 index).
- Dual GeoParquet + GeoJSON output via `dual_write_spatial`
  (`scripts/preprocess/io.py`).
- `HUGE_GEOJSON_THRESHOLD = 100,000` — layers ≥ this skip full-geometry
  GeoJSON and write only simplified.
- `MAP_APP_REHAUL_PLAN.md` (root; subsequently moved to
  `docs/MAP_APP_REHAUL.md` with a DEFERRED status header in Section 1
  of the production-readiness push) with the full 10-phase
  Svelte/PMTiles/DuckDB-WASM rebuild design.

### Fixed

- `CountyScoreToParcelJoin` raised `KeyError: 'distress_tier'` because
  the parcel schema pre-initialized the same column. Fixed by dropping
  the placeholder column before merge. Same defensive guard added to
  `CountyScoreToTowerJoin` and `CountyScoreToSolarJoin`.
- Indiana parcels normalize hung at 3.7M rows in iterrows; flagged for
  Section 5.2 vectorization.
- AR field map originally used wrong column names (`NameOwner`,
  `Address`, `Acres`); corrected to actual AR schema (`OwnerName`,
  `ParcelId`, `CountyFips`, `AdrCity`, `AdrZip5`, `TaxArea`,
  `TotalValue`, `ParcelType`).

### Outcomes by state

- **AR (05):** 2.1M parcels, 9/9 joins, 8 views, 0 warnings.
- **FL (12):** 241K parcels (FGDL DSL state-land — wrong dataset; flagged
  for replacement with `fdor_nal`).
- **IN (18):** 3.7M parcels but no `owner_name`; only `state_summary`
  view built.

---

## 2026-05 — v3 framework scaffolding

### Added

- `scripts/preprocess/` package with registry-driven Normalizer / Join /
  View architecture.
- 11 working normalizers across `scripts/preprocess/normalizers/`.
- Canonical schemas for `parcel`, `tower`, `distress_overlay`,
  `solar_facility`, `billboard`, `county_score` + 9 reserved types.
- `scripts/preprocess/manifest.py` — `PreprocessManifest` with
  freshness check + lineage tracking.
- `scripts/preprocess/runner.py` — orchestration entry points used by
  CLI and puller UI.
- `data/processed/preprocess_manifest.json` (schema v3) recording
  per-source normalize and per-state compose status.

### Deprecated

- `scripts/_legacy/preprocess_v1.py` — the Graham-County-only one-shot.
  Kept for reference; scheduled for removal in Section 5.6 of the
  current production-readiness push.

---

## Late 2025 — v1 puller + first framework

### Added

- `app_puller/` PySide6 desktop application.
- `scripts/fetch/` headless puller library with `DataSource` ABC,
  AutomationPolicy enforcement, atomic `.partial` → `current/`
  promotion.
- 28 raw data sources under `scripts/fetch/sources/`.
- `data/manifest.json` schema v1 (fetch manifest).
- `scripts/verify_raw.py` — per-source filename-signature contents check.
- `scripts/diagnose.py` — LLM-powered verify-failure diagnosis.

---

## Mid 2025 — v0 Graham County one-shot

### Added

- Original `scripts/preprocess.py` — single Python script ingesting
  FCC ASR, NC OneMap parcels for Graham County NC, and HUD Opportunity
  Zones; spatial-joining; producing three GeoJSON files.
- `app/` — Leaflet static SPA with sidebar + filters + details panel.
- `PROJECT_BRIEF.md` — business case + pilot rationale + initial data
  layout. Still authoritative for the business context as of today.

---

## How to update this changelog

When a section of the work plan completes, append a dated entry
summarizing:

- What was **Added** (new files, new features).
- What was **Changed** (renames, restructures).
- What was **Fixed** (bug fixes with one-line description).
- What was **Removed** (deletions; include archive location).
- What was **Deprecated** (kept but flagged for removal).
- What was **Documented** (new docs, significant doc rewrites).

Reference the relevant ADRs in `docs/DECISIONS.md` and section of the
work plan when it's helpful.

Keep entries short — link to commits / PRs once the GitHub repo
exists (Section 2).
