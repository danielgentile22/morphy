# Testing strategy and conventions

**Archived.** This describes the test setup as it stood when the project
stopped. The preprocess, fetch, data TUI, map-app, and backend suites (the
backend's multi-tenancy isolation suite included) were all built. The LLM
lease-extraction eval (§11.3, ADR-059) was planned but never built.

---

## 1. Why we test

Automated tests served four purposes:

1. **Regression protection** as the codebase grew slice by slice (F → A → C → D+E → B).
2. **Schema and API contract enforcement**, so the map app and backend never have to wonder whether a field or endpoint exists.
3. **Documentation by example.** Fixtures and tests are the cheapest way to show how a normalizer, join, view, or API route is supposed to behave.
4. **Trust in the output.** The analyst using the product made real calls based on its numbers. "Every change passes the gating CI checks" is the difference between confident use and checking everything by hand.

---

## 2. Test stack

| Layer | Tool | Why |
|---|---|---|
| **Unit + integration (Python)** | **pytest** | Standard for Python data pipelines; fast; good fixture model |
| **Coverage** | **pytest-cov** | Bundled; report on `scripts/preprocess/` ≥ 70 % |
| **Schema validation** | **jsonschema** | Validates `catalog.json`, `summary.json`, `preprocess_manifest.json` against committed JSON Schemas |
| **Lint / format** | **ruff** | One tool for both lint and format check; fast; opinionated |
| **Type check (backend only)** | **pyright** | Basic mode, scoped to `backend/` (`[tool.pyright]`); the pipeline is deliberately excluded because pandas typing is noise |
| **CI** | **GitHub Actions** | Four merge gates run on every push (see §6) |
| **Frontend tests** | **Vitest** (unit) + **Playwright** (E2E) | Live in `app/tests/`; run with `npm run test:unit` / `test:e2e` (ADR-043) |

The four CI merge gates are `lint.yml` (ruff lint + format, pyright on
`backend/`), `test.yml` (full pytest suite), `frontend.yml` (svelte-check +
vitest + `vite build` for `app/`), and `api-types.yml` (OpenAPI → TypeScript
drift gate). Contract fixtures in `contracts/` back the API-shape tests.

---

## 3. Test layout

The editable install that `uv sync` performs makes `preprocess` / `fetch`
(and the `scripts/` top-level modules) importable as normal packages. There
is no path bootstrapping anywhere, and `tests/test_no_sys_path_hacks.py`
fails the suite if `sys.path` manipulation reappears. Tests are organized by
*feature*, not by stage: one file per major surface area.

```
tests/
├── fixtures/                       Tiny synthetic data committed to the repo
│   └── catalog/                    golden_catalog.json + golden_index.json
│                                   (the only committed fixtures; all other
│                                   test inputs are built synthetically in-test)
│
├── test_app_assets.py              --app-assets pipeline (index.json + facets)
├── test_catalog_schema.py          JSON Schema validation for catalog.json
├── test_compose_loader.py          Per-state input loading
├── test_compose_memory.py          ADR-051 chunked compose memory bound
├── test_compose_property.py        Cluster sizes / tower attach / OZ membership
├── test_county_boundaries.py       County-choropleth GeoJSON output
├── test_county_score_lookup.py     CountyScoreLookupJoin parametric join
├── test_duckdb_equivalence.py      DuckDB-engine ⇄ pandas equivalence
├── test_facets.py                  Per-state facets.json shape + ranges
├── test_fcc_uls.py                 ULS normalizer (carrier match, Slice A)
├── test_fips.py                    State / county FIPS helpers
├── test_index_schema.py            JSON Schema validation for index.json
├── test_infra_to_parcel.py         Parametric InfraToParcelJoin
├── test_owners_index.py            Owners-index schema + build
├── test_per_chunk_joins.py         Per-chunk join correctness (chunked compose)
├── test_pandas_coerce.py           Mixed-dtype coercion edge cases
├── test_parcel_adapter.py          State-parcel adapter framework
├── test_pipeline.py                Pipeline + Severity orchestrator
├── test_preprocess_manifest.py     Manifest rebuild + freshness checks
├── test_puller_resume.py           Storage helpers for resumable fetches
├── test_quality_report.py          ColumnStats / TableStats / QualityReport
├── test_scoring.py                 ScoreComponents + ScoringProfile + weights
├── test_serve.py                   scripts/serve.py byte-range parser
├── test_spatial_attribute_join.py  SpatialAttribute join (OZ / QCT)
├── test_tiles.py                   parcels.pmtiles construction
├── test_typed_artifact.py          Generic typed-artifact validate helper
├── test_uls_to_asr.py              ULS ⨝ ASR carrier join
└── …                               57 test_*.py files total (see `ls tests/`)
```

Abbreviations used above: OZ is an Opportunity Zone, QCT a Qualified Census
Tract, ULS the FCC Universal Licensing System, ASR the FCC Antenna Structure
Registration, and FIPS the Federal Information Processing Standards codes for
states and counties.

Counts at archive time, from `uv run pytest --collect-only -q` (pytest counts
each parametrized case separately): **1,099 tests** in the full run, of which
627 come from the 57 `test_*.py` files under `tests/` and 472 from
`backend/tests/` (43 top-level files plus 3 under `isolation/`, see §11). The
map app's separate suite under `app/tests/` adds 518 Vitest unit tests (from
`npx vitest list`) plus the Playwright E2E specs.

One quirk: collecting `pytest tests` on its own fails on three files
(`test_compose_memory.py`, `test_duckdb_equivalence.py`,
`test_join_registry_names.py`) with `ModuleNotFoundError: No module named
'tests'`. A bare `pytest` from the repo root collects them fine, and so does
running a single unaffected file.

---

## 4. Fixture strategy

Fixtures are tiny synthetic data, not real production samples. Most test
inputs are **built synthetically inside the test** (small in-memory
DataFrames / GeoDataFrames assembled per case). The only committed fixture
files are the data-catalog golden files under `tests/fixtures/catalog/`
(`golden_catalog.json`, `golden_index.json`). There is no `tests/conftest.py`
and no per-source `*_raw/` subdir convention. (`data/` is git-ignored, but
`tests/fixtures/` is not.)

**Rules for synthetic test data:**

- Keep it tiny: a handful of rows per case
- Synthetic only (no real parcel-owner names)
- Cover the edge cases that have bitten us (for example NaN owner names,
  empty extras dicts, multi-polygon geometries, point geometries
  across the antimeridian, county_fips in both 3-digit and 5-digit forms)
- Share a builder helper across tests rather than committing fixture parquet

---

## 5. What's covered

Each line is the test file → what it covers.

* **Compose**: `test_compose_loader.py` (per-state input loading),
  `test_compose_property.py` (cluster sizes, tower attach, OZ
  membership; this replaced the old single-shot-vs-chunked snapshot
  comparison), `test_compose_memory.py` (ADR-051 chunked-compose
  memory bound).
* **Joins**: `test_infra_to_parcel.py` (the parametric
  `InfraToParcelJoin` blueprint and its tower / solar / billboard
  instantiations), `test_county_score_lookup.py` (parcel ⨝
  county_score), `test_spatial_attribute_join.py` (OZ / QCT overlay
  attach).
* **Scoring**: `test_scoring.py` (ScoreComponents, ScoringProfile,
  apply_weights; per [ADR-058](./adr/0058-tunable-transparent-scoring.md)).
* **App-asset pipeline**: `test_app_assets.py` (`--app-assets` output
  shape), `test_facets.py` (per-state facets.json), `test_county_boundaries.py`
  (county GeoJSON), `test_tiles.py` (parcels.pmtiles construction).
* **Schema validation**: `test_catalog_schema.py`,
  `test_index_schema.py`, `test_typed_artifact.py` (generic helper).
* **Quality and lineage**: `test_quality_report.py` (ColumnStats /
  TableStats), `test_pipeline.py` (Pipeline + Severity orchestrator),
  `test_preprocess_manifest.py` (manifest rebuild + freshness).
* **Normalizer support code**: `test_parcel_adapter.py` (state-parcel
  adapter framework), `test_pandas_coerce.py` (mixed-dtype coercion
  edge cases), `test_fips.py` (FIPS helpers).
* **Puller and data TUI**: `test_puller_resume.py` (storage helpers for
  resumable fetches), `test_data_tui.py` (the Textual TUI, driven through
  Textual's `Pilot` test API), `test_composite_verify.py` (the pre-deploy
  composite verify step).
* **Range server**: `test_serve.py` (`_parse_byte_range`).

Known gaps when the project stopped:

* One test per normalizer. Only the state-parcel normalizer and a few others
  have direct tests. Most are exercised transitively by the compose-property
  tests.
* One test per view. The 8 views under `scripts/preprocess/views/` have no
  direct row-count assertions.
* The pure-function pieces of `scripts/verify_raw.py` and
  `scripts/diagnose.py` have no tests.

---

## 6. How to run

```bash
# Local: full suite (uv sync once to build .venv from uv.lock)
source .venv/bin/activate
pytest

# With coverage (sources configured in pyproject [tool.coverage.run])
pytest --cov --cov-report=term-missing

# Subset
pytest tests/test_compose_property.py -v
```

Pre-commit:

```bash
# Recommended pre-commit hook; mirrors the lint + test CI gates
ruff check . && ruff format --check . && uv run pyright && pytest -q
```

CI has four merge gates, all required:

- `lint.yml`: `ruff check .` + `ruff format --check .`, plus `pyright`
  scoped to `backend/`.
- `test.yml`: `uv run --no-sync pytest --cov --cov-report=term-missing`
  on every push (coverage printed to the job log; no codecov or PR-comment
  step).
- `frontend.yml`: svelte-check + vitest + `vite build` for `app/`.
- `api-types.yml`: the regenerated `backend/openapi.json` and
  `app/src/lib/api-types.ts` must match the committed artifacts (OpenAPI →
  TypeScript drift gate).

---

## 7. Coverage targets

| Module | Target line coverage |
|---|---|
| `scripts/preprocess/base.py` | ≥ 80 % |
| `scripts/preprocess/compose.py` | ≥ 75 % |
| `scripts/preprocess/manifest.py` | ≥ 80 % |
| `scripts/preprocess/io.py` | ≥ 80 % |
| `scripts/preprocess/normalizers/*.py` | ≥ 60 % (each) |
| `scripts/preprocess/joins/*.py` | ≥ 80 % (each) |
| `scripts/preprocess/views/*.py` | ≥ 70 % (each) |
| **Overall `scripts/preprocess/`** | ≥ 70 % |

Normalizers get a lower target because their long-tail format-handling code
is hard to exercise from synthetic fixtures.

---

## 8. What's NOT tested (intentionally)

- **`scripts/fetch/sources/*` against live endpoints.** Integration tests
  against real endpoints are flaky. Fetch mechanics are tested with mocked
  HTTP, and live behavior was verified by hand through the TUI. (The old Qt
  puller, formerly the untested-UI entry here, was retired; its Textual
  successor has `Pilot`-driven tests in the CI gate.)
- **`app/` from the pytest suite.** The map app has its own test
  stack: Vitest unit tests + Playwright E2E in `app/tests/` (run from
  `app/`, not via pytest). `pytest` covers only the Python backend and
  the app-asset preprocess scripts.
- **Performance.** Separate benchmark scripts; not part of the CI gate.

---

## 9. Adding new tests

When you add:

- A new **normalizer** → test in `tests/test_<source>.py` (one file per
  source surface), building a small synthetic raw sample in-test.
- A new **join** → either add it to an existing `test_<join>.py`
  module (if it instantiates one of the existing blueprints:
  `InfraToParcelJoin`, `SpatialAttributeJoin`, `CountyScoreLookupJoin`)
  or start a new `test_<your_join>.py` next to its siblings.
- A new **view** → start `tests/test_<view_name>.py`; assert row count,
  columns, and at least one expected value. (View tests are sparse.)
- A new **canonical type** → add it to `CURRENT_SCHEMA_VERSIONS`, and add a
  normalizer test that builds a small synthetic sample and emits it.

The convention is **one test file per major surface**. New surfaces get
new files; we don't bucket into `test_normalizers.py` / `test_joins.py`
catch-alls.

---

## 10. Sentinel "the whole thing works" test

The canary is `test_compose_property.py`. It builds a fully synthetic
single-state compose against fixture data and asserts the key invariants
(cluster sizes, infra↔parcel attach, OZ membership,
infrastructure_summary content). Extending it to also assert ≥ 9 joins
applied and ≥ 8 views built was considered; the per-surface tests guard
those counts instead.

---

## 11. Backend additions (D + E): backend, LLM, multi-tenancy

The hosted-private backend ([ADR-055](./adr/0055-hosted-private-backend.md),
narrowed by ADR-064) belongs to the D + E slice. The backend and its
multi-tenancy isolation suite were built and deployed. The LLM
lease-extraction eval (§11.3, [ADR-059](./adr/0059-llm-lease-extraction.md))
was planned but never built.

### 11.1 Backend HTTP API (built)

- **Tool:** `pytest`. The suite defaults to **SQLite** (behaviorally
  equivalent for the schema); real Postgres via **testcontainers** runs
  only when `MORPHY_TEST_TESTCONTAINERS=1` is set (starting it by default
  was dropped as too slow), or against a running server via
  `MORPHY_TEST_DATABASE_URL`.
- **Coverage:** 472 collected tests across 46 files under `backend/tests/`:
  the auth flow (username/password login → identity-only `morphy_session`
  cookie), lead CRUD and the status ladder, tasks, owner merge, scoring
  presets, per-request credential authority, the read-only gate and demo
  login (`test_read_only_demo.py`, which enumerates every non-GET route and
  asserts 403 for a read-only principal), migrations, the OpenAPI export,
  and more.
- **Layout:** flat `backend/tests/test_*.py` (one file per surface) plus
  the `isolation/` subdir below. See `backend/tests/` and `backend/CLAUDE.md`.

### 11.2 Multi-tenancy isolation (built)

- **Tool:** pytest fixtures with 2 synthetic tenants seeded in the test DB,
  under `backend/tests/isolation/` (`test_tenant_isolation.py`,
  `test_tenant_isolation_api.py`, `test_tenant_isolation_api_surfaces.py`;
  marker `tenant_isolation`).
- **Coverage:** every API route gets a "tenant A user cannot read / write /
  list tenant B's data" test. Run with `pytest -m tenant_isolation` (31
  tests at archive time).
- **Why it matters:** teams ARE tenants (ADR-063). The tenant is resolved
  from the signed-in user's team on every request, and the isolation suite
  proves the boundary holds.

### 11.3 LLM extraction eval (planned, never built)

The plan, kept for its reasoning:

- **Tool:** a dedicated gold-set runner as a **separate CI job** (`pytest -m llm_eval`).
- **Gold set:** 20 hand-labeled leases, each with a JSON of expected field values and page citations.
- **Metrics:** per-field precision, recall, exact match.
- **Gating:** a PR would block if any field's accuracy dropped below an 85% bar.
- **Manual-override label:** `eval-override-acknowledged` on PRs that intentionally change the extraction schema and need the gold set re-labeled.
- **Build-time guidance:** prompt caching, a tool-use schema for structured output, and per-field model selection ([ADR-059](./adr/0059-llm-lease-extraction.md)).

### 11.4 Data audits as CI (planned; partly built outside CI)

- **Plan:** bash and Python checks run post-compose: zero `warnings` in
  `summary.json` per anchor state, the expected join count (≥ 9), no missing
  canonical columns, no negative `interestingness_score`, and per-state record
  counts within ±10% of the prior compose. A PR would block if a state's
  compose broke, catching the AR/MT-class data-quality regressions before
  they ship.
- **What was built:** no CI job, since CI has no real data to compose.
  Instead the data TUI's verify step (`scripts/data_tui/verify.py`) diffs the
  fresh composite against the last deploy receipt (per-state parcel and tower
  counts with a 10% drop threshold, owners-index schema version and row count,
  file inventory) and blocks a deploy on any failed check unless the user
  logs an explicit override. `tests/test_composite_verify.py` covers it.

### 11.5 Per-slice test-coverage bar

Beyond §7's overall coverage targets, the target was that **each slice ships
with ≥ 70% line coverage of the new code added in that slice**. That lifts
overall coverage gradually rather than retrofitting it at the end.

### 11.6 Backend test layout

The backend tests use a **flat** layout (one `test_*.py` per surface, plus
the `isolation/` subdir), not the originally planned `api/`, `extraction/`,
`tenants/` package split. The LLM-extraction tests (`gold_set/`, the
`llm_eval` marker) were never built.

```
backend/
├── app/                             # about 30 modules (auth_service, lead_store,
│                                    #   owners_index_service, task_store, …)
└── tests/
    ├── conftest.py                  # SQLite by default; opt-in testcontainers
    │                                #   Postgres via MORPHY_TEST_TESTCONTAINERS=1
    ├── test_auth.py                 # + test_api.py, test_lead_store.py,
    │                                #   test_api_tasks.py, test_credential_authority.py,
    │                                #   test_migration.py, … (43 files)
    └── isolation/
        ├── test_tenant_isolation.py          # marker: tenant_isolation
        ├── test_tenant_isolation_api.py
        └── test_tenant_isolation_api_surfaces.py

frontend / app/: Vitest unit + Playwright E2E, per §2.
```
