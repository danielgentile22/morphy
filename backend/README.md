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

- `lead(tenant_id, display_cluster_id, status, notes, contact_name, contact_phone, contact_email, best_channel, created_at, updated_at)` — PK `(tenant_id, display_cluster_id)`. The `contact_*` columns (Slice 3 / #49) are the team's **editable** outreach record, distinct from the read-only mailing address served from source parcel data. Added to an existing DB by the additive `init_db` migration (`db._migrate_added_columns`; a stand-in until Alembic).
- `contact_attempt(id, tenant_id, display_cluster_id, occurred_on, channel, outcome, note, created_at)` — manual outreach events **and** auto-logged status-transition rows (`channel='status'`) share this one activity stream.
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
| GET | `/api/my-leads` | owners advanced **off** New — the My-Leads kanban worklist (Slice 5 / #51); each carries its status so the client buckets it into a lane |
| GET | `/api/counts` | live nav counts `{candidates, my_leads}` (the index partitions into the two surfaces) |
| GET | `/api/leads/{display_cluster_id}` | full Lead: owner rollup + **holdings** (per-parcel structures + EPSG:4326 footprint) + read-only **mailing address** + tallest tower + lead state + editable contact fields + attempts |
| PUT | `/api/leads/{display_cluster_id}` | set status, notes, and/or contact fields (validates the ladder; a drag on the kanban is just a status PUT) |
| POST | `/api/leads/{display_cluster_id}/attempts` | append a manual contact attempt (date · channel · outcome) |

The read half of the full Lead page (holdings / mailing / tallest tower) is
served from the precomputed **owners index** (schema **v3** —
`scripts/preprocess/owners_index.py`). v2 (Slice 3 / #49) added per-owner
`holdings`, `mailing_address`, and `tallest_tower_height_m`; **v3 (Slice 6 /
#52)** added the owner-level filter rollups the shared top-bar `FilterModel`
reads — `counties`, `active_tower_count`, `structure_count`, `structure_types`
— surfaced on `OwnerSummary` (`/api/candidates`, `/api/my-leads`) and also
written to a slim client companion `owners_filter.json` (filter+search fields
only, no holdings) the map loads to narrow towers. Only the lead state is
per-tenant. Rebuild both after composing states: `python scripts/preprocess.py
--owners-index` (writes `owners_index.json` + `owners_filter.json`). New
`OwnerSummary` fields are **defaulted** so a pre-v3 index still validates.

Every data route resolves the tenant from the `Authorization: Bearer <jwt>`
(`current_tenant_id`, now JWT-derived) and is tenant-scoped; an
unauthenticated data request is rejected with **401**.

## Auth (magic-link, Slice 2 / #48 — ADR-055)

1. `POST /api/auth/request-link {email}` — the user is provisioned into the
   default tenant (`DEFAULT_TENANT_ID`, `1`), a 256-bit random token is
   generated, its **SHA-256 hash** is stored (the raw token is never
   persisted or logged), and a link is handed to the pluggable
   `EmailSender`. Always responds `200` (no email enumeration), and is
   per-email rate-limited. In dev (`AUTH_DEV_MODE=1`) the raw token is echoed
   as `dev_token` so the SPA can finish the exchange without a real inbox.
2. `POST /api/auth/exchange {token}` — a still-valid token is **atomically**
   redeemed **once** (a conditional `UPDATE … WHERE used_at IS NULL`, so two
   concurrent redemptions can't both win) for an HS256 JWT carrying
   `tid`/`sub`/`email`. Reused, expired, or unknown tokens all fail
   identically (`400`).
3. Send the JWT as `Authorization: Bearer <jwt>` on every data route.

### Posture: fail closed (`AUTH_DEV_MODE`)

A single switch gates the auth posture. It is **off by default** (the safe,
prod state). With it off, the app **refuses to start** unless `AUTH_JWT_SECRET`
is set and a sign-in gate exists (`AUTH_ALLOWED_EMAILS`, or an explicit
`AUTH_ALLOW_OPEN_SIGNUP=1`); the raw-token echo is forced off regardless of
`AUTH_EXPOSE_TOKEN`; and booting with the dev `ConsoleEmailSender` is rejected.
Set `AUTH_DEV_MODE=1` for the zero-config local loop (ephemeral secret, token
echo, open sign-up), so the dev convenience never leaks into prod by accident.

Auth environment variables:

| Var | Default | Purpose |
|---|---|---|
| `AUTH_DEV_MODE` | `0` (prod) | **master safety switch.** `1` = local dev (ephemeral secret + token echo + open sign-up). Off ⇒ the prereqs below are enforced at boot. |
| `AUTH_JWT_SECRET` | _(required off-dev)_ | HS256 signing secret — **set from the host secret store in prod (#16); never commit.** Ephemeral per-process value in dev. |
| `AUTH_SESSION_TTL_DAYS` | `2` | session JWT lifetime (no revocation, so kept short — see trade-offs) |
| `AUTH_LINK_TTL_MINUTES` | `15` | magic-link token lifetime |
| `DEFAULT_TENANT_ID` | `1` | tenant new sign-ins land in (ADR-055 "reads 1 for now") |
| `AUTH_ALLOWED_EMAILS` | _(empty)_ | comma-separated sign-in allowlist. **Required off-dev** unless `AUTH_ALLOW_OPEN_SIGNUP=1`. |
| `AUTH_ALLOW_OPEN_SIGNUP` | `0` | explicit opt-in to open auto-provisioning when off-dev (else an allowlist is required) |
| `AUTH_EXPOSE_TOKEN` | `1` (dev) | echo the raw token in the request-link response — **honored only when `AUTH_DEV_MODE=1`; always off in prod** |
| `AUTH_LINK_RATE_MAX` | `5` | max request-link tokens per email per window |
| `AUTH_LINK_RATE_WINDOW_MINUTES` | `15` | rolling rate-limit window |

### Security model & trade-offs (Slice 2)

- **JWT in `localStorage` (SPA).** An XSS could read it and exfiltrate the
  session. Accepted for an internal, single-tenant tool, and mitigated by
  Svelte's default escaping of all rendered PII (owner names, notes). The more
  secure alternative — an httpOnly + SameSite cookie with CSRF handling — is
  deliberately deferred (a larger change touching CORS + the SPA fetch layer).
- **No server-side revocation / logout.** Sessions are stateless JWTs valid
  until `exp`; `signOut()` only clears the client. The blast radius of a leaked
  token is bounded by the (now 2-day) TTL. A `jti`/token-version denylist is a
  future option if revocation becomes a requirement.
- **No `aud`/`iss` claims.** Fine while one secret signs for one audience; add
  them if this secret is ever shared across services.
- **Prod deploy checklist (ties to #16).** Set `AUTH_DEV_MODE=0`,
  `AUTH_JWT_SECRET` (host secret store), a non-empty `AUTH_ALLOWED_EMAILS` (or
  `AUTH_ALLOW_OPEN_SIGNUP=1` only if open sign-up is truly intended), and wire a
  real `EmailSender`. The app now refuses to boot if any of these is missing.

## Run

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt          # fastapi, sqlalchemy, uvicorn, PyJWT (+ optional psycopg/testcontainers)

# 1. precompute the owners index (reads the composed anchor states on disk)
python scripts/preprocess.py --app-assets         # ensures parcels_attr.parquet exists
python scripts/preprocess.py --owners-index        # writes composite/owners_index.json (+ owners_filter.json)

# 2. run the API (SQLite dev DB at data/processed/lead_state.sqlite3 by default).
#    AUTH_DEV_MODE=1 opts into the local loop; without it the app fails closed
#    (it requires a real AUTH_JWT_SECRET + a sign-in gate — see "fail closed").
AUTH_DEV_MODE=1 uvicorn backend.app.main:app --reload --port 8000
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
`DATABASE_URL=postgresql+psycopg://user:pass@host/db`. In prod leave
`AUTH_DEV_MODE` off and follow the deploy checklist above (set
`AUTH_JWT_SECRET` from the host secret store, a sign-in gate, and a real
`EmailSender`, #16) — the app refuses to boot otherwise.

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
