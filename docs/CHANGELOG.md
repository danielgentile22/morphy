# CHANGELOG

**Last updated:** 2026-05-19

History of meaningful changes to the project. Newest at the top.
Format follows [Keep a Changelog](https://keepachangelog.com/)
loosely; semver isn't enforced because this isn't a released package.

Changes are grouped under section headers (`Added` / `Changed` /
`Fixed` / `Removed` / `Deprecated` / `Documented`).

---

## Unreleased — production-readiness push (in progress)

Active work plan in `/.claude/plans/cached-wobbling-token.md`.

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
