# Lead-triage write-layer backend

The first backend code in the repo (ADR-055 / ADR-061), introduced by
Slice 1 (#47). A tenant-shaped FastAPI + SQLAlchemy service that holds the
**write layer** — Lead status, notes, and contact attempts — on top of the
static, read-only cross-state **owners index** the preprocess pipeline
precomputes (`scripts/preprocess/owners_index.py` →
`data/processed/composite/owners_index.json`).

The analytical read-layer (PMTiles, DuckDB-WASM, catalog GeoJSON) is
unchanged and lives in `app/` + `data/processed/composite/`. This backend
never imports the preprocess framework; it only *reads* its JSON output.

## Layout

```
backend/app/
  config.py                 env-driven settings (DATABASE_URL, OWNERS_INDEX_PATH, stub tenant)
  db.py                     SQLAlchemy engine/session (SQLite dev default, Postgres via env)
  models.py                 ORM: lead, contact_attempt (tenant_id on every table)
  lead_status.py            status ladder + transition rules (parity w/ app/src/lib/lead-status.ts)
  lead_store.py             LeadStore — tenant-scoped CRUD + auto-logged status transitions
  owners_index_service.py   serves the static index left-joined with the tenant's lead state
  auth.py                   current_tenant_id() — stubbed to 1 (magic-link auth is Slice 2)
  main.py                   FastAPI routes
backend/tests/              LeadStore + tenant-isolation (testcontainers Postgres → SQLite fallback)
```

## Schema (tenant-shaped, ADR-055)

- `lead(tenant_id, display_cluster_id, status, notes, created_at, updated_at)` — PK `(tenant_id, display_cluster_id)`.
- `contact_attempt(id, tenant_id, display_cluster_id, occurred_on, channel, outcome, note, created_at)` — also receives auto-logged status-transition rows (`channel='status'`).

## Lead status ladder

```
New ──▶ Researching ──▶ Contacted ──┬──▶ Interested ──▶ In Business
                                    └──▶ Uninterested   (terminal)
```

Default `new`. `uninterested` and `in_business` are terminal; `in_business`
is reachable only via `interested`. Illegal moves (e.g. `new → in_business`)
are rejected (HTTP 409).

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + owners-indexed count |
| GET | `/api/candidates?limit=` | owners at New, ranked by interestingness |
| GET | `/api/leads/{display_cluster_id}` | owner rollup + lead state + attempts |
| PUT | `/api/leads/{display_cluster_id}` | set status and/or notes (validates the ladder) |

Every route resolves a tenant via `current_tenant_id` (stubbed `1`) and is
tenant-scoped.

## Run

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt          # fastapi, sqlalchemy, uvicorn (+ optional psycopg/testcontainers)

# 1. precompute the owners index (reads the composed anchor states on disk)
python scripts/preprocess.py --app-assets         # ensures parcels_attr.parquet exists
python scripts/preprocess.py --owners-index        # writes composite/owners_index.json

# 2. run the API (SQLite dev DB at data/processed/lead_state.sqlite3 by default)
uvicorn backend.app.main:app --reload --port 8000
# health check:
curl localhost:8000/api/health
```

Point at Postgres instead of SQLite with
`DATABASE_URL=postgresql+psycopg://user:pass@host/db`.

## Test

```bash
source .venv/bin/activate
pytest backend/tests -v          # or just `pytest` (testpaths includes backend/tests)
```

The multi-tenancy isolation test uses **testcontainers Postgres** when
Docker is available (TESTING.md §11.1); it falls back to SQLite when Docker
is absent (set `PILOT_TEST_DATABASE_URL` to force a specific Postgres).
