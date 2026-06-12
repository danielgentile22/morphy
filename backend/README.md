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
  models.py                 ORM: lead, contact_attempt, app_user, owner_cluster_override (tenant_id on every table)
  lead_status.py            status ladder + transition rules (parity w/ app/src/lib/lead-status.ts)
  lead_store.py             LeadStore — tenant-scoped CRUD + auto-logged status transitions
  owner_merge_service.py    OwnerMergeService — manual merge/split overrides (display_cluster_id = coalesce(override, raw))
  owners_index_service.py   serves the static index (override-aware) left-joined with the tenant's lead state
  auth.py                   JWT issue/verify + cookie/bearer extraction + current_tenant_id
  password.py               stdlib PBKDF2-HMAC-SHA256 hashing (no third-party dep; `python -m app.password`)
  credentials.py            the users.txt import format — parse/load + shared auth result types (ADR-069)
  credentials_store.py      the credential table: three-way authenticate, writers, fail-closed boot (ADR-069)
  users.py                  user-management CLI shell (`python -m app.users`, #87; DB-backed)
  tenant_service.py         team → tenant resolution, registration-order (#86)
  login_throttle.py         in-process (ip, username) brute-force throttle (Slice 2 / #77)
  auth_service.py           login() (username/password) + user provisioning
  main.py                   FastAPI routes
backend/tests/              LeadStore + auth + tenant-isolation (testcontainers Postgres → SQLite fallback)
```

## Schema (tenant-shaped, ADR-055)

- `lead(tenant_id, display_cluster_id, status, notes, contact_name, contact_phone, contact_email, best_channel, created_at, updated_at)` — PK `(tenant_id, display_cluster_id)`. The `contact_*` columns (Slice 3 / #49) are the team's **editable** outreach record, distinct from the read-only mailing address served from source parcel data. Added to an existing DB by the additive `init_db` migration (`db._migrate_added_columns`; a stand-in until Alembic).
- `contact_attempt(id, tenant_id, display_cluster_id, occurred_on, channel, outcome, note, created_at)` — manual outreach events **and** auto-logged status-transition rows (`channel='status'`) share this one activity stream.
- `tenant(id, name UNIQUE, created_at)` — a **team** (#86, ADR-063). Teams ARE tenants; team isolation is the ADR-055 tenant isolation. Registered find-or-create in credentials-file order, so the first team in the file owns tenant 1 (the pre-teams board). Rows are never deleted.
- `app_user(id, tenant_id, email UNIQUE, created_at)` — a person who can sign in (email = the username, stored opaquely). Synced to their current team's tenant on every login/request (#88).
- `owner_cluster_override(tenant_id, source_cluster_id, target_cluster_id, created_at)` — manual merge overrides (Slice 7 / #53). PK `(tenant_id, source_cluster_id)`. Keyed on **raw** cluster ids, so overrides survive an owners-index recompute (raw ids in the parquet are never mutated).

## Manual owner merge/split (Slice 7 / #53, ADR-056)

The conservative cross-state resolver errs toward *not* merging (a false merge
= a wrong-person call). `OwnerMergeService` is the manual net: it lets a tenant
**merge** two owner-clusters or **split** one apart via the
`owner_cluster_override` table. The whole contract is the resolution rule

```
display_cluster_id = coalesce(override_target, raw_cluster_id)
```

— `OwnerMergeService.resolve()` follows the override chain (A→B→C) to a fixed
point. The read layer (`OwnersIndexService.effective()`) applies it in **one
place**, so a merge/split shows up identically on every served surface (the
map's tower→landowner resolution, Candidates, My-Leads, counts, the Lead page)
— resolution is never forked per surface. With no overrides (the common case)
the static index is returned untouched.

**Lead-state reconciliation (target-wins).** Merge/split write **only** the
override table — never the `lead` / `contact_attempt` tables. A merged owner is
served under the surviving **target** id, and its lead state reconciles across
the member clusters by *target-wins*: the target's own row is authoritative for
the scalar fields (status / notes / contact_*), while contact-attempt streams
**concatenate** across all members (so the full outreach history stays visible).
Writes resolve the requested id → target and persist on the target row, so what
you see is what you validate and write. **Split** deletes the source's override
row; because no lead state was ever moved, the source re-emerges with its own
state intact and the target keeps its own — the operation is perfectly
reversible. (Consequence: merging adopts the *target's* status, not the
source's; the source's history remains visible in the merged stream and is
fully restored on split. A merge-time "inherit the furthest-along status" seed
was considered and rejected to keep merge/split non-destructive and reversible.)

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
| POST | `/api/auth/login` | **username/password → identity-only session JWT** (the front door, #76/#84/#88); sets the `pilot_session` httpOnly cookie (ADR-069) and returns the token in the body for non-browser clients; brute-force throttled (#77) |
| POST | `/api/auth/logout` | clear the session cookie — ends the browser's API *and* `/data` access (ADR-069) |
| GET | `/api/auth/check` | forward-auth seam for the edge `/data/processed/*` gate (ADR-069): cookie/bearer valid + username still credentialed → 204, else 401; no body |
| GET | `/api/auth/me` | the authenticated username + tenant + **team** (#86) |
| GET | `/api/health` | liveness + owners-indexed count (public) |
| GET | `/api/candidates?limit=` | owners at New, ranked by interestingness |
| GET | `/api/my-leads` | owners advanced **off** New — the My-Leads kanban worklist (Slice 5 / #51); each carries its status so the client buckets it into a lane |
| GET | `/api/counts` | live nav counts `{candidates, my_leads}` (the index partitions into the two surfaces) |
| GET | `/api/leads/{display_cluster_id}` | full Lead: owner rollup + **holdings** (per-parcel structures + EPSG:4326 footprint) + read-only **mailing address** + tallest tower + lead state + editable contact fields + attempts |
| PUT | `/api/leads/{display_cluster_id}` | set status, notes, and/or contact fields (validates the ladder; a drag on the kanban is just a status PUT) |
| POST | `/api/leads/{display_cluster_id}/attempts` | append a manual contact attempt (date · channel · outcome) |
| POST | `/api/leads/{display_cluster_id}/merge` | merge another owner-cluster (`source_cluster_id`) into this Lead — the path id is the survivor (Slice 7 / #53) |
| POST | `/api/leads/{display_cluster_id}/split` | split a merged-in cluster (`source_cluster_id`) back out to its own raw cluster |

The read half of the full Lead page (holdings / mailing / tallest tower) is
served from the precomputed **owners index** (schema **v4** —
`scripts/preprocess/owners_index.py`). v2 (Slice 3 / #49) added per-owner
`holdings`, `mailing_address`, and `tallest_tower_height_m`; **v3 (Slice 6 /
#52)** added the owner-level filter rollups the shared top-bar `FilterModel`
reads — `counties`, `active_tower_count`, `structure_count`, `structure_types`
— surfaced on `OwnerSummary` (`/api/candidates`, `/api/my-leads`) and also
written to a slim client companion `owners_filter.json` (filter+search fields
only, no holdings) the map loads to narrow towers; **v4 (Slice A / #28)** adds
`carriers` (the ULS spectrum licensee(s) — `{carrier_name, callsign,
license_expiry, confidence_tag}`) onto each tower **structure** inside a
holding. The `Structure` response model **declares** `carriers` — an
undeclared field would be silently dropped by `response_model=LeadDetail`, so
the carrier list would never reach the Lead page. Only the lead state is
per-tenant. Rebuild both after composing states: `python scripts/preprocess.py
--owners-index` (writes `owners_index.json` + `owners_filter.json`). New
`OwnerSummary` / `Structure` fields are **defaulted** so a pre-v4 index still
validates.

Every data route verifies the session JWT — the `pilot_session` httpOnly
cookie first (ADR-069; the SPA's transport), then `Authorization: Bearer`
(tests, curl) — and resolves the tenant by re-checking the **credential
table** on that very request (`current_tenant_id` → `resolve_principal`,
#88 / ADR-063 as amended by ADR-069) — the store, never the token, decides
authorization. An unauthenticated request, or one whose username has no
credential row anymore, is rejected with **401**. Non-GET routes additionally
pass an Origin/Referer CSRF check (cookie transport's backstop; non-browser
clients without those headers pass).

## User management (the `credential` table + CLI, #87 / ADR-069)

Credentials live in the app database — the **`credential`** table (normalized
unique username, self-describing PBKDF2 hash, team) that Litestream already
replicates. **The CLI is the management surface — never edit hashes by hand:**

```bash
cd backend
python -m app.users add <username> <team>       # prompts for a password (hidden)
python -m app.users remove <username>           # locked out on their next request
python -m app.users list                        # usernames + teams only, never hashes
python -m app.users set-password <username>     # prompts; old password stops working
python -m app.users set-team <username> <team>  # moves the user to another team's board
python -m app.users import-file <path>          # one-shot users.txt migration (refuses a non-empty table)
```

The CLI writes the same `DATABASE_URL` the backend serves from (on the Fly
machine that's the volume DB). **Registration order matters:** the first
credential's team owns tenant 1 — the original lead board (#86; `id` order
replaced file order). `import-file` preserves the file's line order for
exactly that reason.

**One runtime endpoint is a sanctioned caller of this writer** (PRD #121,
[ADR-068](../docs/adr/0068-self-service-password-change.md), re-homed onto the
store by ADR-069): `POST /api/me/password {current_password, new_password}`
lets a signed-in user change **their own** password from Settings → Account.
It calls `users.change_password`, which verifies the current password
(constant-time) and rotates the hash through the same store writer the CLI
uses (team + registration order untouched — live on the next login attempt).
Wrong current password → 401; nothing written. The username comes from the
verified principal, never the body, so a caller can only rotate their own
credential.

## Per-user settings (`UserSetting`, PRD #121)

The first *per-user* persisted preference layer (the backend was tenant-shaped
until now). `UserSetting` is a generic key/value table keyed
`(tenant_id, user_id, key)`; `UserSettingsStore` mirrors `SettingsStore` with
baked-in defaults so a user who never opened Settings still reads sane values.
Routes are scoped by **both** ids from the resolved principal:

```
GET  /api/me/settings   → resolved per-user prefs (defaults filled in)
PUT  /api/me/settings   → upsert one or more keys; returns the resolved prefs
PUT  /api/me            → update the signed-in user's display_name
```

Keys: `theme`, `colorblind`, `basemap`, `view_mode`, `home_view`,
`filter_default`, `filter_default_apply`. `home_view` and `filter_default` are
**opaque JSON blobs the client owns** — persisted + served verbatim, never
inspected (same posture as `ScoringPreset.config`). New prefs slot in as new
keys with no schema change.

## Auth (username/password, ADR-062 + ADR-063 as amended by ADR-069)

The live front door is `POST /api/auth/login {username, password}`. Credentials
live in the **`credential` table** (see "User management" above). Usernames and
teams are case-insensitive (trimmed + lowercased); the password is verified
constant-time against a stdlib PBKDF2-HMAC-SHA256 hash (`app/password.py`, no
third-party dependency). A wrong password and an unknown username are
*distinguishable* 401s (a deliberate usability-over-enumeration call, with the
enumeration exposure bounded by the throttle). In dev (`AUTH_DEV_MODE=1`) a
built-in `dev`/`dev` credential on a built-in `dev` team is seeded at boot
**through the same store-writer path the CLI uses**, so the loop needs zero
config and dev can't hide credential-resolution bugs.

On success the route mints an HS256 session JWT that carries **identity only**
(`sub` = the username — no tenant, no team) and sets it in the
**`pilot_session` httpOnly / Secure / SameSite=Lax cookie** (ADR-069 — the
SPA's transport; page scripts can never read it, and it rides automatically on
MapLibre/PMTiles/DuckDB-WASM data fetches, which is what lets Caddy gate
`/data/processed/*` via `forward_auth` → `GET /api/auth/check`). The body still
returns the token for non-browser clients; `Authorization: Bearer <jwt>` stays
accepted, the cookie checked first. `POST /api/auth/logout` clears the cookie.
**The credential table is authoritative on every request** (#88): each request
re-checks that the username still has a row and resolves its *current* team →
that team's tenant scopes the request. Consequences:

- **Removing a user** (`python -m app.users remove`) locks them out on their
  very next request — API *and* data plane — no waiting out the session TTL,
  no restart.
- **Moving a user to another team** (`set-team`) re-homes their live session on
  its next request; the old team's data is untouched.
- Nothing a token carries — even forged extra claims signed with a leaked
  secret — can grant access the store doesn't currently grant.

### Brute-force throttle (#77)

`POST /api/auth/login` is guarded by an in-process sliding-window failure
counter (`app/login_throttle.py`) keyed by `(client IP, username)`. After
`AUTH_LOGIN_THROTTLE_MAX` failed attempts within
`AUTH_LOGIN_THROTTLE_WINDOW_SECONDS`, further attempts for that key get **429**
(with a `Retry-After` header) — even a correct password is refused while
blocked. There is **no hard lockout**: the block self-clears as the window rolls
forward, and a successful login resets the key. Because the IP is part of the
key, an attacker who knows a username can't weaponize it to lock a real user out
(no lockout-DoS). State is per-process (fine on the single VM; it resets on
restart, and is not shared across replicas).

### Posture: fail closed (`AUTH_DEV_MODE`)

A single switch gates the auth posture. It is **off by default** (the safe,
prod state). With it off, the app **refuses to serve** unless **both**
`AUTH_JWT_SECRET` is set **and** the credential table has at least one row
(`credentials_store.ensure_fail_closed_boot`, run at startup) — so a deploy
can be neither open (no secret) nor impossible to log into (no credential).
Set `AUTH_DEV_MODE=1` for the zero-config local loop (ephemeral secret +
built-in `dev`/`dev` login seeded through the same store writer), so the dev
convenience never leaks into prod by accident.

#### Revocation & the kill switch

Two operational levers, both immediate (no restart, no extra tooling):

- **Revoke one user:** `python -m app.users remove <username>`. The credential
  table is authoritative on every request (#88), so they are locked out on
  their very next click — even with a valid, unexpired session JWT.
- **Kill every session at once:** rotate `AUTH_JWT_SECRET`. Every already-issued
  JWT was signed by the old secret, so all of them fail verification at once and
  every user must log in again. This is the global panic button for a suspected
  token leak.

Auth environment variables:

| Var | Default | Purpose |
|---|---|---|
| `AUTH_DEV_MODE` | `0` (prod) | **master safety switch.** `1` = local dev (ephemeral secret + built-in `dev`/`dev` login). Off ⇒ the prereqs below are enforced at startup. |
| `AUTH_JWT_SECRET` | _(required off-dev)_ | HS256 signing secret — **set from the host secret store in prod (#16); never commit.** Ephemeral per-process value in dev. Rotating it invalidates every active session (kill switch). |
| `AUTH_LOGIN_THROTTLE_MAX` | `5` | failed logins per `(ip, username)` before 429 within the window |
| `AUTH_LOGIN_THROTTLE_WINDOW_SECONDS` | `300` | sliding throttle window (block self-clears as it rolls forward; no hard lockout) |
| `AUTH_SESSION_TTL_DAYS` | `30` | session JWT lifetime — purely a convenience window now; authorization is re-checked against the credential table on every request (#88) |

### Security model & trade-offs

- **The session rides in an httpOnly cookie** (ADR-069) — page scripts can't
  read it, so an XSS can't exfiltrate the session. CSRF posture: SameSite=Lax
  plus the Origin/Referer middleware on non-GET routes — no token-dance
  machinery for a same-origin internal tool.
- **Sessions are identity-only; the credential table authorizes every
  request** (#88, ADR-063/069). A leaked token is only as useful as the store
  allows right now: remove the username and the token is dead on the next
  request — including `/data` fetches, which the edge gates through
  `/api/auth/check`. The 30-day TTL bounds how long an *unrevoked* identity
  stays signed in, nothing more.
- **No `aud`/`iss` claims.** Fine while one secret signs for one audience; add
  them if this secret is ever shared across services.
- **Login throttle is per-process.** The brute-force counter lives in memory on
  one VM; it resets on restart and isn't shared across replicas. Acceptable for
  the single-VM deployment — a shared store (Redis) is the move if it ever scales
  horizontally. (The credential table itself is replica-safe: every process
  reads the same DB.)
- **Prod deploy checklist (ties to #16).** Set `AUTH_DEV_MODE=0`,
  `AUTH_JWT_SECRET` (host secret store), and create at least one credential
  (`python -m app.users add`, or `import-file` for a legacy users.txt). The
  app refuses to serve otherwise.

## Run

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt          # fastapi, sqlalchemy, uvicorn, PyJWT (+ optional psycopg/testcontainers)

# 1. precompute the owners index (reads the composed anchor states on disk)
python scripts/preprocess.py --app-assets         # ensures parcels_attr.parquet exists
python scripts/preprocess.py --owners-index        # writes composite/owners_index.json (+ owners_filter.json)

# 2. run the API (SQLite dev DB at data/processed/lead_state.sqlite3 by default).
#    AUTH_DEV_MODE=1 opts into the local loop; without it the app fails closed
#    (it requires a real AUTH_JWT_SECRET + ≥1 credential row — see "fail closed").
AUTH_DEV_MODE=1 uvicorn backend.app.main:app --reload --port 8000
# health check (public):
curl localhost:8000/api/health

# 3. sign in (dev: the built-in dev/dev credential)
JWT=$(curl -s localhost:8000/api/auth/login \
  -H 'content-type: application/json' -d '{"username":"dev","password":"dev"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl localhost:8000/api/candidates -H "authorization: Bearer $JWT"   # 200; without the header → 401
```

Point at Postgres instead of SQLite with
`DATABASE_URL=postgresql+psycopg://user:pass@host/db`. In prod leave
`AUTH_DEV_MODE` off and follow the deploy checklist above (set
`AUTH_JWT_SECRET` from the host secret store and create at least one
credential with `python -m app.users add`) — the app refuses to serve
otherwise.

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
