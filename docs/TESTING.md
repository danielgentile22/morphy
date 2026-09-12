# TESTING — Strategy & Conventions

**Last updated:** 2026-07-03
**Status:** Preprocess + fetch + data-TUI + map-app + backend test suites are
live (the backend and its multi-tenancy isolation suite have shipped to
production). Only the LLM lease-extraction eval (§11.3, ADR-059) remains
forward-looking.

---

## 1. Why we test

For a co-founder-facing product, automated tests serve four purposes:

1. **Regression protection** as the codebase evolves slice by slice (F → A → C → D+E → B).
2. **Schema + API contract enforcement** so the map app and backend never have to wonder whether a field / endpoint exists.
3. **Documentation by example** — fixtures + tests are the cheapest way to show how a normalizer / join / view / API route is supposed to behave.
4. **Co-founder trust** — when the co-founder is making real calls based on the product's output, "every shipped change passes the gating CI checks" is the difference between confident use and ad-hoc verification.

---

## 2. Test stack

| Layer | Tool | Why |
|---|---|---|
| **Unit + integration (backend)** | **pytest** | Standard for Python data pipelines; fast; great fixture model |
| **Coverage** | **pytest-cov** | Bundled; report on `scripts/preprocess/` ≥ 70 % |
| **Schema validation** | **jsonschema** | Validates `catalog.json`, `summary.json`, `preprocess_manifest.json` against committed JSON Schemas |
| **Lint / format** | **ruff** | Single tool for both lint and format check; fast; opinionated |
| **Type check (backend only)** | **pyright** | Basic mode, scoped to `backend/` ([tool.pyright]); the pipeline is deliberately excluded — pandas typing is noise (PRD #136) |
| **CI** | **GitHub Actions** | Four merge gates run on every push (see §6) |
| **Frontend tests** | **Vitest** (unit) + **Playwright** (E2E) | Live in `app/tests/`; run with `npm run test:unit` / `test:e2e` (ADR-043) |

The four CI merge gates are: `lint.yml` (ruff lint + format, pyright on
`backend/`), `test.yml` (full pytest suite), `frontend.yml` (svelte-check +
vitest + `vite build`, run for both `app/` and `audit-site/`), and
`api-types.yml` (OpenAPI → TypeScript drift gate). Contract fixtures
(PRD #137, `contracts/`) back the API-shape tests.

---

## 3. Test layout

The editable install that `uv sync` performs (PRD #132) makes `preprocess`
/ `fetch` (and the `scripts/` top-level modules) importable as normal
packages — there is no path bootstrapping anywhere, and
`tests/test_no_sys_path_hacks.py` fails the suite if `sys.path`
manipulation reappears. Tests are organized by *feature*, not by stage —
one file per major surface area.

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
├── test_duckdb_equivalence.py      DuckDB-engine ⇄ pandas equivalence (PRD #135)
├── test_facets.py                  Per-state facets.json shape + ranges
├── test_fcc_uls.py                 ULS normalizer (carrier match — Slice A)
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
├── test_puller_status.py           Puller status + attention decisions
├── test_quality_report.py          ColumnStats / TableStats / QualityReport
├── test_scoring.py                 ScoreComponents + ScoringProfile + weights
├── test_serve.py                   scripts/serve.py byte-range parser
├── test_spatial_attribute_join.py  SpatialAttribute join (OZ / QCT)
├── test_tiles.py                   parcels.pmtiles construction
├── test_typed_artifact.py          Generic typed-artifact validate helper
├── test_uls_to_asr.py              ULS ⨝ ASR carrier join
└── …                               42 test_*.py files total (see `ls tests/`)
```

Total: **~368 test functions** across 42 `test_*.py` files. The map-app's
separate suite (Vitest + Playwright under `app/tests/`) adds another ~349 unit
tests on top, and the shipped backend has its own ~45-file suite under
`backend/tests/` (see §11).

---

## 4. Fixture strategy

Fixtures are tiny synthetic data — not real production samples. Most test
inputs are now **built synthetically inside the test** (small in-memory
DataFrames / GeoDataFrames assembled per case); the only committed fixture
files are the data-catalog golden files under `tests/fixtures/catalog/`
(`golden_catalog.json`, `golden_index.json`). There is no `tests/conftest.py`
and no per-source `*_raw/` subdir convention. (data/ is git-ignored, but
`tests/fixtures/` is not.)

**Rules for synthetic test data:**

- Keep it tiny — a handful of rows per case
- Synthetic only (no real parcel-owner names)
- Cover the edge cases that have bitten us (e.g., NaN owner names,
  empty extras dicts, multi-polygon geometries, point geometries
  across the antimeridian, county_fips both 3-digit and 5-digit forms)
- Share a builder helper across tests rather than committing fixture parquet

---

## 5. What's covered today

Reality reflects the cleanup-of-code pass through 2026-05-27. Each line is
the test file → what it covers.

* **Compose** — `test_compose_loader.py` (per-state input loading),
  `test_compose_property.py` (cluster sizes, tower attach, OZ
  membership; this replaces the old single-shot-vs-chunked snapshot
  comparison), `test_compose_memory.py` (ADR-051 chunked-compose
  memory bound).
* **Joins** — `test_infra_to_parcel.py` (the parametric
  `InfraToParcelJoin` blueprint, tower / solar / billboard
  instantiations), `test_county_score_lookup.py` (parcel ⨝
  county_score), `test_spatial_attribute_join.py` (OZ / QCT overlay
  attach).
* **Scoring** — `test_scoring.py` (ScoreComponents, ScoringProfile,
  apply_weights; per [ADR-058](./adr/0058-tunable-transparent-scoring.md)).
* **App-asset pipeline** — `test_app_assets.py` (`--app-assets` output
  shape), `test_facets.py` (per-state facets.json), `test_county_boundaries.py`
  (county GeoJSON), `test_tiles.py` (parcels.pmtiles construction).
* **Schema validation** — `test_catalog_schema.py`,
  `test_index_schema.py`, `test_typed_artifact.py` (generic helper).
* **Quality + lineage** — `test_quality_report.py` (ColumnStats /
  TableStats), `test_pipeline.py` (Pipeline + Severity orchestrator),
  `test_preprocess_manifest.py` (manifest rebuild + freshness).
* **Normalizer support code** — `test_parcel_adapter.py` (state-parcel
  adapter framework), `test_pandas_coerce.py` (mixed-dtype coercion
  edge cases), `test_fips.py` (FIPS helpers).
* **Puller** — `test_puller_resume.py` (storage helpers for resumable
  fetches), `test_puller_status.py` (status + attention decisions —
  pure functions, no Qt).
* **Range server** — `test_serve.py` (`_parse_byte_range`).

Notable gaps to fill (carried as future commits, not as "design"):

* One-test-per-normalizer parity — only state-parcel + a few others
  have direct tests today. Most are exercised transitively by the
  compose-property tests.
* One-test-per-view — the 8 views under `scripts/preprocess/views/`
  have no direct row-count assertions yet.
* `scripts/verify_raw.py` + `scripts/diagnose.py` pure-function pieces
  have no tests.

---

## 6. How to run

```bash
# Local — full suite (uv sync once to build .venv from uv.lock)
source .venv/bin/activate
pytest

# With coverage (sources configured in pyproject [tool.coverage.run])
pytest --cov --cov-report=term-missing

# Subset
pytest tests/test_compose_property.py -v
```

Pre-commit:

```bash
# Recommended pre-commit hook — mirrors the lint + test CI gates
ruff check . && ruff format --check . && uv run pyright && pytest -q
```

CI — four merge gates, all required:

- `lint.yml` — `ruff check .` + `ruff format --check .`, plus `pyright`
  scoped to `backend/` (PRD #136).
- `test.yml` — `uv run --no-sync pytest --cov --cov-report=term-missing`
  on every push (coverage printed to the job log; no codecov / PR-comment
  step).
- `frontend.yml` — svelte-check + vitest + `vite build`, run for both
  `app/` and `audit-site/`.
- `api-types.yml` — regenerated `backend/openapi.json` + `app/src/lib/
  api-types.ts` must match the committed artifacts (OpenAPI → TypeScript
  drift gate, PRD #133).

---

## 7. Coverage targets + budget

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

Lower coverage on normalizers reflects the long-tail format-handling
code that's hard to exercise from synthetic fixtures.

---

## 8. What's NOT tested (intentionally)

- **`scripts/fetch/sources/*` against live endpoints** — integration
  tests against real endpoints are flaky; fetch mechanics are tested
  with mocked HTTP, live behavior verified manually via the TUI.
  (The Qt puller — formerly the untested-UI entry here — was retired
  in #240; its Textual successor has pilot tests in the CI gate.)
- **`app/` from the pytest suite** — the map app has its own test
  stack: Vitest unit tests + Playwright E2E in `app/tests/` (run from
  `app/`, not via pytest). `pytest` covers only the Python backend +
  the app-asset preprocess scripts.
- **Performance** — separate benchmark scripts; not part of CI gate.

---

## 9. Adding new tests

When you add:

- A new **normalizer** → test in `tests/test_<source>.py` (one file per
  source surface), building a small synthetic raw sample in-test.
- A new **join** → either add it to an existing `test_<join>.py`
  module (if it instantiates one of the existing blueprints —
  `InfraToParcelJoin`, `SpatialAttributeJoin`, `CountyScoreLookupJoin`)
  or start a new `test_<your_join>.py` next to its siblings.
- A new **view** → start `tests/test_<view_name>.py`; assert row count
  + columns + at least one expected value. (View tests are sparse today.)
- A new **canonical type** → add to `CURRENT_SCHEMA_VERSIONS`, add a
  normalizer test that builds a small synthetic sample and emits it.

The convention is **one test file per major surface**. New surfaces get
new files; we don't bucket into `test_normalizers.py` / `test_joins.py`
catch-alls.

---

## 10. Sentinel "the whole thing works" test

The canary today is `test_compose_property.py` — it builds a fully-
synthetic single-state compose against fixture data and asserts the
key invariants (cluster sizes, infra↔parcel attach, OZ membership,
infrastructure_summary content). A future commit may extend it to
also assert ≥ 9 joins applied and ≥ 8 views built; for now those
counts are guarded by the per-surface tests instead.

---

## 11. Backend additions (D + E) — backend + LLM + multi-tenancy

The hosted-private backend ([ADR-055](./adr/0055-hosted-private-backend.md),
narrowed by ADR-064) belongs to the D + E slice. The backend and its
multi-tenancy isolation suite have **shipped and are deployed in
production**; only the LLM lease-extraction eval (§11.3,
[ADR-059](./adr/0059-llm-lease-extraction.md)) is still unbuilt.

### 11.1 Backend HTTP API — shipped

- **Tool:** `pytest`. The suite defaults to **SQLite** (behaviourally
  equivalent for the schema); real Postgres via **testcontainers** runs
  only when `PILOT_TEST_TESTCONTAINERS=1` is set (auto-starting it by
  default was dropped — too slow).
- **Coverage:** ~45 test files under `backend/tests/` — auth flow
  (username/password login → identity-only `pilot_session` cookie),
  lead CRUD + status ladder, tasks, owner merge, scoring presets,
  per-request credential authority, the Ask-Claude SSE endpoint, and more.
- **Layout:** flat `backend/tests/test_*.py` (one file per surface) plus
  the `isolation/` subdir below. See `backend/tests/` + `backend/CLAUDE.md`.

### 11.2 Multi-tenancy isolation — shipped

- **Tool:** pytest fixtures with 2 synthetic tenants seeded in the test DB,
  under `backend/tests/isolation/` (`test_tenant_isolation.py` +
  `test_tenant_isolation_api.py`, `@pytest.mark.tenant_isolation`).
- **Coverage:** every API route gets a "tenant A user cannot read / write /
  list tenant B's data" test. Run with `pytest -m tenant_isolation`.
- **Why it matters:** teams ARE tenants (ADR-063) — tenant is resolved from
  the signed-in user's team on every request; the isolation suite proves the
  boundary holds.

### 11.3 LLM extraction eval

- **Tool:** dedicated gold-set runner as a **separate CI job** (`pytest -m llm_eval`).
- **Gold-set:** 20 hand-labelled leases. Each lease has a JSON of expected field values + page citations.
- **Metrics:** per-field precision, recall, exact-match.
- **Gating:** PR blocks if any field's accuracy drops below the 85% bar (per-slice gate in [SCOPE.md §4](./SCOPE.md)).
- **Manual-override label:** `eval-override-acknowledged` on PRs that intentionally change the extraction schema and need the gold-set re-labelled.
- **Build-time guidance:** use the `claude-api` skill — it handles prompt caching, Tool use schema, model selection ([ADR-059](./adr/0059-llm-lease-extraction.md)).

### 11.4 Data audits as CI

- **Tool:** bash + python checks run post-compose.
- **Coverage:** zero `warnings` in `summary.json` per anchor state; expected join count (≥ 9); no missing canonical columns; no negative `interestingness_score`; per-state record counts within ±10% of prior compose.
- **Gating:** PR blocks if a state's compose breaks. Catches the AR/MT-class data-quality regressions before they ship.

### 11.5 Per-slice test-coverage bar

Beyond §7's overall coverage targets: **each slice ships with ≥ 70% line coverage of the new code added in that slice.** Lifts overall coverage gradually rather than retrofitting at the end. Per [SCOPE.md §4](./SCOPE.md).

### 11.6 Shipped backend test layout

The backend tests live in a **flat** layout — one `test_*.py` per surface,
plus the `isolation/` subdir — not the planned `api/`, `extraction/`,
`tenants/` package split. The LLM-extraction tests (`gold_set/`, the
`llm_eval` marker) are not built yet.

```
backend/
├── app/                             # ~40 modules (auth_service, lead_store,
│                                    #   owners_index_service, ask_client, …)
└── tests/
    ├── conftest.py                  # SQLite by default; opt-in testcontainers
    │                                #   Postgres via PILOT_TEST_TESTCONTAINERS=1
    ├── test_auth.py                 # + test_api.py, test_lead_store.py,
    │                                #   test_api_tasks.py, test_credential_authority.py,
    │                                #   test_api_ask.py, … (~45 files)
    └── isolation/
        ├── test_tenant_isolation.py      # marker: tenant_isolation
        └── test_tenant_isolation_api.py

frontend / app/  — Vitest unit + Playwright E2E continue per §2.
```
