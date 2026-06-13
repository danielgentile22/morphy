# TESTING — Strategy & Conventions

**Last updated:** 2026-05-27
**Status:** Preprocess + fetch + app_puller + map-app test suites are live. Slice 4 backend / LLM / multi-tenancy sections (§11) are forward-looking.

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
| **CI** | **GitHub Actions** | Lint + tests run on every push (Section 6.3) |
| **Frontend tests** | **Vitest** (unit) + **Playwright** (E2E) | Live in `app/tests/`; run with `npm run test:unit` / `test:e2e` (ADR-043) |

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
│   ├── ar_state_parcels_raw/       ESRI .json sample (mirrors AR Open Data)
│   ├── mt_cadastral_raw/           Same pattern for MT
│   ├── nc_onemap_parcels_raw/      NC OneMap paginated geojson sample
│   ├── arc_distressed_raw/         ARC + USDA + LBNL minimal fixtures
│   └── …                           One subdir per source that has tests
│
├── test_app_assets.py              --app-assets pipeline (index.json + facets)
├── test_catalog_schema.py          JSON Schema validation for catalog.json
├── test_compose_loader.py          Per-state input loading
├── test_compose_memory.py          ADR-051 chunked compose memory bound
├── test_compose_property.py        Cluster sizes / tower attach / OZ membership
├── test_county_boundaries.py       County-choropleth GeoJSON output
├── test_county_score_lookup.py     CountyScoreLookupJoin parametric join
├── test_facets.py                  Per-state facets.json shape + ranges
├── test_fips.py                    State / county FIPS helpers
├── test_index_schema.py            JSON Schema validation for index.json
├── test_infra_to_parcel.py         Parametric InfraToParcelJoin
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
└── test_typed_artifact.py          Generic typed-artifact validate helper
```

Total: **241 tests** at 2026-05-27. The map-app's separate suite (Vitest +
Playwright under `app/tests/`) adds another ~212 unit tests on top.

---

## 4. Fixture strategy

Fixtures are tiny synthetic data — not real production samples — so
they can be committed to the repo (data/ is git-ignored, but
`tests/fixtures/` is not).

**Rules for fixtures:**

- ≤ 50 rows per parquet
- Synthetic only (no real parcel-owner names)
- Cover the edge cases that have bitten us (e.g., NaN owner names,
  empty extras dicts, multi-polygon geometries, point geometries
  across the antimeridian, county_fips both 3-digit and 5-digit forms)
- Reusable across multiple tests via `conftest.py` fixtures

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
  apply_weights; per [ADR-058](./adr/0058-tunable-scoring-seam.md)).
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
* One-test-per-view — the 9 views under `scripts/preprocess/views/`
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

# Watch mode (requires pytest-watch)
ptw
```

Pre-commit:

```bash
# Recommended pre-commit hook (Section 6.3)
ruff check . && ruff format --check . && uv run pyright && pytest -q
```

CI:

`.github/workflows/test.yml` runs `pytest` on every push; reports
coverage as a comment on PRs (via codecov action or a similar tool).

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

- **`scripts/fetch/sources/*`** — these talk to live HTTP endpoints.
  Integration tests against real endpoints are flaky; we rely on
  manual verification via the puller.
- **`app_puller/`** — Qt UI; manual click-through verification only.
- **`app/` from the pytest suite** — the map app has its own test
  stack: Vitest unit tests + Playwright E2E in `app/tests/` (run from
  `app/`, not via pytest). `pytest` covers only the Python backend +
  the app-asset preprocess scripts.
- **Performance** — separate benchmark scripts; not part of CI gate.

---

## 9. Adding new tests

When you add:

- A new **normalizer** → fixture in `tests/fixtures/<source>_raw/`,
  test in `tests/test_<source>.py` (one file per source surface).
- A new **join** → either add it to an existing `test_<join>.py`
  module (if it instantiates one of the existing blueprints —
  `InfraToParcelJoin`, `SpatialAttributeJoin`, `CountyScoreLookupJoin`)
  or start a new `test_<your_join>.py` next to its siblings.
- A new **view** → start `tests/test_<view_name>.py`; assert row count
  + columns + at least one expected value. (View tests are sparse today.)
- A new **canonical type** → add to `CURRENT_SCHEMA_VERSIONS`, add a
  fixture parquet, add a normalizer test that emits it.

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

## 11. Slice 4 additions — backend + LLM + multi-tenancy

Slice 4 (D + E) stands up a hosted-private backend ([ADR-055](./adr/0055-hosted-private-backend.md)) with LLM-based lease extraction ([ADR-059](./adr/0059-llm-lease-extraction.md)). The test surface grows substantially.

### 11.1 Backend HTTP API

- **Tool:** `pytest` + **`testcontainers-postgres`** (real Postgres in Docker per test session).
- **Why real Postgres:** SQLite differs from Postgres on JSON ops, FTS, isolation levels — bugs that hide in SQLite bite in prod.
- **Coverage:** all routes; auth flow (username/password login → session JWT); lead CRUD; lease CRUD; activity-log append; scoring-profile persistence.
- **Layout:** `backend/tests/api/test_<resource>.py`. Conftest spins one Postgres per session; per-test transaction rolls back.

### 11.2 Multi-tenancy isolation

- **Tool:** pytest fixtures with 2 synthetic tenants seeded in the test DB.
- **Coverage:** every API route gets a "tenant A user cannot read / write / list tenant B's data" test. Run with `pytest -k tenant_isolation`.
- **Why now even though we're single-tenant:** the boundary needs to hold from Day 1 (ADR-055 tenant-shaped schema). Tests stay correct when a second tenant joins.

### 11.3 LLM extraction eval

- **Tool:** dedicated gold-set runner as a **separate CI job** (`pytest -m llm_eval`).
- **Gold-set:** 20 hand-labelled leases. Each lease has a JSON of expected field values + page citations.
- **Metrics:** per-field precision, recall, exact-match.
- **Gating:** PR blocks if any field's accuracy drops below the 85% bar (per-slice gate in [GOALS.md §3](./GOALS.md)).
- **Manual-override label:** `eval-override-acknowledged` on PRs that intentionally change the extraction schema and need the gold-set re-labelled.
- **Build-time guidance:** use the `claude-api` skill — it handles prompt caching, Tool use schema, model selection ([ADR-059](./adr/0059-llm-lease-extraction.md)).

### 11.4 Data audits as CI

- **Tool:** bash + python checks run post-compose.
- **Coverage:** zero `warnings` in `summary.json` per anchor state; expected join count (≥ 9); no missing canonical columns; no negative `interestingness_score`; per-state record counts within ±10% of prior compose.
- **Gating:** PR blocks if a state's compose breaks. Catches the AR/MT-class data-quality regressions before they ship.

### 11.5 Per-slice test-coverage bar

Beyond §7's overall coverage targets: **each slice ships with ≥ 70% line coverage of the new code added in that slice.** Lifts overall coverage gradually rather than retrofitting at the end. Per [GOALS.md §3](./GOALS.md).

### 11.6 Slice 4 layout

```
backend/
├── app/
│   ├── api/
│   ├── auth/
│   ├── leads/
│   ├── leases/
│   ├── extraction/
│   └── tenants/
└── tests/
    ├── conftest.py                  # testcontainers-postgres + tenant fixtures
    ├── api/
    │   ├── test_auth.py
    │   ├── test_leads.py
    │   ├── test_leases.py
    │   └── test_activity.py
    ├── isolation/
    │   └── test_tenant_isolation.py  # marker: tenant_isolation
    ├── extraction/
    │   ├── gold_set/                 # 20 hand-labelled leases (gitignored if PDFs; manifests checked in)
    │   ├── test_extraction_eval.py   # marker: llm_eval
    │   └── test_extraction_unit.py
    └── data_audits/
        └── test_state_composes.py    # post-compose audit gates

frontend / app/  — Vitest unit + Playwright E2E continue per §2.
```
