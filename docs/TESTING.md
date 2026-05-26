# TESTING — Strategy & Conventions

**Last updated:** 2026-05-25
**Status:** Pre-implementation for the preprocess test suite + Slice 4 backend / LLM / multi-tenancy surfaces. This document is the design.

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
| **CI** | **GitHub Actions** | Lint + tests run on every push (Section 6.3) |
| **Frontend tests** | **Vitest** (unit) + **Playwright** (E2E) | Live in `app/tests/`; run with `npm run test:unit` / `test:e2e` (ADR-043) |

---

## 3. Test layout

```
tests/
├── __init__.py                  Marks the package
├── conftest.py                  Shared pytest fixtures (paths, sample contexts)
├── fixtures/
│   ├── parcel.parquet           ~50 rows synthetic parcel
│   ├── tower.parquet            ~30 rows synthetic FCC ASR shape
│   ├── distress_overlay.parquet ~10 rows synthetic OZ + QCT
│   ├── solar_facility.parquet   ~10 rows synthetic
│   ├── county_score.parquet     ~20 rows synthetic
│   ├── ar_parcels_raw_sample/   Tiny .gdb-like sample for state_parcels test
│   └── catalog_baseline.json    Expected catalog after fixture compose
├── test_normalizers.py          One test per active normalizer
├── test_joins.py                One test per join
├── test_views.py                One test per view
├── test_compose.py              End-to-end synthetic compose
├── test_manifest.py             Manifest rebuild + freshness checks
├── test_schemas.py              JSON Schema validation
└── test_io.py                   dual_write_spatial, huge-layer threshold
```

Total target: **≥ 30 tests** at Section 6 exit; **≥ 70 % line coverage**
of `scripts/preprocess/`.

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

## 5. Test categories

### 5.1 Normalizer tests (`test_normalizers.py`)

One test per active normalizer:

```python
def test_state_parcels_normalize_arkansas(fixture_ar_raw_dir, tmp_path):
    """Given fixture raw AR data, produces canonical parcel parquet."""
    result = AR_Normalizer().normalize(fixture_ar_raw_dir, tmp_path)
    df = pd.read_parquet(tmp_path / "parcels.parquet")
    assert result.canonical_rows == len(df)
    assert "owner_name" in df.columns
    assert "owner_kind" in df.columns
    assert df["state_fips"].unique().tolist() == ["05"]
```

Coverage targets:

- Each normalizer: input fixture → expected row count + schema.
- Each normalizer: handles NaN inputs without crashing.
- Each normalizer: produces system columns (`_source`,
  `_processed_at`, `_schema_version`).
- Each parcel normalizer: produces non-empty `owner_kind` distribution.

### 5.2 Join tests (`test_joins.py`)

One test per join. Construct a fixture `ComposeContext`, apply the
join, assert the resulting table has the expected columns.

```python
def test_tower_to_parcel_join_attaches_parcel_id(ctx_with_parcels_and_towers):
    TowerToParcelJoin().apply(ctx_with_parcels_and_towers)
    towers = ctx_with_parcels_and_towers.get("tower")
    assert "parcel_id" in towers.columns
    assert towers["parcel_id"].notna().sum() > 0
```

Critical join test: `safe_merge` helper drops pre-existing columns
correctly (the bug pattern from ADR-020).

### 5.3 View tests (`test_views.py`)

One test per view. Given fixture context with the right canonical
types loaded, view returns expected row count + columns.

### 5.4 Compose end-to-end (`test_compose.py`)

Build a fully-synthetic single-state compose:

```python
def test_compose_synthetic_state_produces_valid_catalog(tmp_path, monkeypatch):
    """End-to-end: synthetic state compose produces a valid catalog.json."""
    monkeypatch.setattr("scripts.preprocess.COMPOSITE_ROOT", tmp_path)
    cfg = ComposeConfig(state=STATES["99"])  # synthetic state FIPS
    result = compose(cfg)
    catalog = json.loads((tmp_path / "99" / "catalog.json").read_text())
    assert validate_catalog(catalog) is None
    assert "parcels" in catalog["layers"]
```

### 5.5 Manifest tests (`test_manifest.py`)

- `PreprocessManifest.rebuild_from_disk()` produces expected entries.
- Freshness logic: `is_normalize_fresh()` returns True/False correctly.
- Schema-version migration.

### 5.6 Schema validation tests (`test_schemas.py`)

- Each fixture catalog validates against `catalog.schema.json`.
- Each fixture summary validates against `summary.schema.json`.
- Invalid catalog raises a clear error.

### 5.7 I/O tests (`test_io.py`)

- `dual_write_spatial` writes both parquet + geojson for small layers.
- `dual_write_spatial` skips full geojson for huge layers.
- `_prep_complex_cols` JSON-encodes dict/list cells.

---

## 6. How to run

```bash
# Local — full suite
source .venv/bin/activate
pytest

# With coverage
pytest --cov=scripts.preprocess --cov-report=term-missing

# Subset
pytest tests/test_normalizers.py -v

# Watch mode (requires pytest-watch)
ptw
```

Pre-commit:

```bash
# Recommended pre-commit hook (Section 6.3)
ruff check . && ruff format --check . && pytest -q
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
  test in `test_normalizers.py`.
- A new **join** → fixture context fixture in `conftest.py`, test in
  `test_joins.py`.
- A new **view** → test in `test_views.py`; assert row count +
  columns + at least one expected value.
- A new **canonical type** → add to `CURRENT_SCHEMA_VERSIONS`, add a
  fixture parquet, add a normalizer test that emits it.

---

## 10. Sentinel "the whole thing works" test

`test_compose.py::test_full_smoke` runs a compose against fixture data approximating each anchor state and asserts:

- 0 warnings in summary.json
- ≥ 9 joins applied
- ≥ 8 views built
- catalog.json validates against schema

This is the canary that fires when any change breaks the data pipeline.

---

## 11. Slice 4 additions — backend + LLM + multi-tenancy

Slice 4 (D + E) stands up a hosted-private backend ([ADR-055](./adr/0055-hosted-private-backend.md)) with LLM-based lease extraction ([ADR-059](./adr/0059-llm-lease-extraction.md)). The test surface grows substantially. See `docs/grill-2026-05-25-summary.md §Testing additions (Q14)` for the full rationale.

### 11.1 Backend HTTP API

- **Tool:** `pytest` + **`testcontainers-postgres`** (real Postgres in Docker per test session).
- **Why real Postgres:** SQLite differs from Postgres on JSON ops, FTS, isolation levels — bugs that hide in SQLite bite in prod.
- **Coverage:** all routes; auth flow (magic-link request → token → session); lead CRUD; lease CRUD; activity-log append; scoring-profile persistence.
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
