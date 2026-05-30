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
  config.py                 env-driven settings (DATABASE_URL, OWNERS_INDEX_PATH, auth knobs)
  db.py                     SQLAlchemy engine/session (SQLite dev default, Postgres via env)
  models.py                 ORM: lead, contact_attempt, app_user, magic_link_token (tenant_id on every table)
  lead_status.py            status ladder + transition rules (parity w/ app/src/lib/lead-status.ts)
  lead_store.py             LeadStore — tenant-scoped CRUD + auto-logged status transitions
  owners_index_service.py   serves the static index left-joined with the tenant's lead state
  auth.py                   token hashing + JWT issue/verify + current_tenant_id (JWT-derived)
  auth_service.py           AuthService — magic-link request → exchange (hashed one-time tokens)
  email_sender.py           pluggable link delivery (ConsoleEmailSender dev / RecordingEmailSender tests)
  main.py                   FastAPI routes
backend/tests/              LeadStore + auth + tenant-isolation (testcontainers Postgres → SQLite fallback)
```

## Schema (tenant-shaped, ADR-055)

- `lead(tenant_id, display_cluster_id, status, notes, created_at, updated_at)` — PK `(tenant_id, display_cluster_id)`.
- `contact_attempt(id, tenant_id, display_cluster_id, occurred_on, channel, outcome, note, created_at)` — also receives auto-logged status-transition rows (`channel='status'`).
- `app_user(id, tenant_id, email UNIQUE, created_at)` — a person who can sign in, bound to one tenant.
- `magic_link_token(id, tenant_id, user_id, email, token_hash, expires_at, used_at, created_at)` — sign-in tokens **hashed at rest** (only the SHA-256 hash is stored), one-time (`used_at`), short expiry.

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
| POST | `/api/auth/request-link` | email → store a hashed one-time token + send a link |
| POST | `/api/auth/exchange` | valid token → short-lived session JWT |
| GET | `/api/auth/me` | the authenticated tenant + email |
| GET | `/api/health` | liveness + owners-indexed count (public) |
| GET | `/api/candidates?limit=` | owners at New, ranked by interestingness |
| GET | `/api/leads/{display_cluster_id}` | owner rollup + lead state + attempts |
| PUT | `/api/leads/{display_cluster_id}` | set status and/or notes (validates the ladder) |

Every data route resolves the tenant from the `Authorization: Bearer <jwt>`
(`current_tenant_id`, now JWT-derived) and is tenant-scoped; an
unauthenticated data request is rejected with **401**.

## Auth (magic-link, Slice 2 / #48 — ADR-055)

1. `POST /api/auth/request-link {email}` — the user is provisioned into the
   default tenant (`DEFAULT_TENANT_ID`, `1`), a 256-bit random token is
   generated, its **SHA-256 hash** is stored (the raw token is never
   persisted or logged), and a link is handed to the pluggable
   `EmailSender`. Always responds `200` (no email enumeration). In dev
   (`AUTH_EXPOSE_TOKEN=1`) the raw token is echoed as `dev_token` so the SPA
   can finish the exchange without a real inbox.
2. `POST /api/auth/exchange {token}` — a still-valid token is redeemed
   **once** (marked `used_at`) for an HS256 JWT carrying `tid`/`sub`/`email`.
   Reused, expired, or unknown tokens all fail identically (`400`).
3. Send the JWT as `Authorization: Bearer <jwt>` on every data route.

Auth environment variables:

| Var | Default | Purpose |
|---|---|---|
| `AUTH_JWT_SECRET` | ephemeral random (dev) | HS256 signing secret — **set from the host secret store in prod (#16); never commit** |
| `AUTH_SESSION_TTL_DAYS` | `7` | session JWT lifetime |
| `AUTH_LINK_TTL_MINUTES` | `15` | magic-link token lifetime |
| `DEFAULT_TENANT_ID` | `1` | tenant new sign-ins land in (ADR-055 "reads 1 for now") |
| `AUTH_ALLOWED_EMAILS` | _(empty = open)_ | optional comma-separated sign-in allowlist |
| `AUTH_EXPOSE_TOKEN` | `1` (dev) | echo the raw token in the request-link response — **set `0` in prod** |

## Run

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt          # fastapi, sqlalchemy, uvicorn, PyJWT (+ optional psycopg/testcontainers)

# 1. precompute the owners index (reads the composed anchor states on disk)
python scripts/preprocess.py --app-assets         # ensures parcels_attr.parquet exists
python scripts/preprocess.py --owners-index        # writes composite/owners_index.json

# 2. run the API (SQLite dev DB at data/processed/lead_state.sqlite3 by default)
uvicorn backend.app.main:app --reload --port 8000
# health check (public):
curl localhost:8000/api/health

# 3. sign in (dev: the raw token is echoed in the response)
TOKEN=$(curl -s localhost:8000/api/auth/request-link \
  -H 'content-type: application/json' -d '{"email":"you@example.com"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["dev_token"])')
JWT=$(curl -s localhost:8000/api/auth/exchange \
  -H 'content-type: application/json' -d "{\"token\":\"$TOKEN\"}" \
  | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl localhost:8000/api/candidates -H "authorization: Bearer $JWT"   # 200; without the header → 401
```

Point at Postgres instead of SQLite with
`DATABASE_URL=postgresql+psycopg://user:pass@host/db`. In prod set
`AUTH_JWT_SECRET` (from the host secret store) and `AUTH_EXPOSE_TOKEN=0`,
and wire a real `EmailSender` (#16).

## Test

```bash
source .venv/bin/activate
pytest backend/tests -v          # or just `pytest` (testpaths includes backend/tests)
```

The tests default to **SQLite** (fast, reliable; Slice 1's tenant isolation
is application-level, so SQLite exercises the same behavior). Opt into real
Postgres (TESTING.md §11.1) either way:

```bash
PILOT_TEST_DATABASE_URL=postgresql://user:pass@localhost/test pytest backend/tests   # a running Postgres
PILOT_TEST_TESTCONTAINERS=1 pytest backend/tests                                      # spin one via Docker
```
