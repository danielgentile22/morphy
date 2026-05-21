# CHANGELOG

**Last updated:** 2026-05-20

History of meaningful changes to the project. Newest at the top.
Format follows [Keep a Changelog](https://keepachangelog.com/)
loosely; semver isn't enforced because this isn't a released package.

Changes are grouped under section headers (`Added` / `Changed` /
`Fixed` / `Removed` / `Deprecated` / `Documented`).

---

## Unreleased — production-readiness push (in progress)

As of 2026-05-20, Sections 1–3 are done, Section 4 complete for AR/MT
(FL raw intact; NC raw deleted and needs re-fetch), and Section 5's
code is written but **not yet committed** (last commit `a067a49`).
FL/NC compose is blocked pending a chunked-compose refactor (ADR-051).
See [STATUS.md](./STATUS.md) for the current snapshot.

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
