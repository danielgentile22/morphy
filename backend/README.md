# Lead-triage write-layer backend

The first backend code in the repo (ADR-055, ADR-061), introduced by
Slice 1. A tenant-shaped FastAPI + SQLAlchemy service that holds the
**write layer** (Lead status, notes, and contact attempts) on top of the
static, read-only cross-state **owners index** the preprocess pipeline
precomputes (`scripts/preprocess/owners_index.py` →
`data/processed/composite/owners_index.json`).

The analytical read layer (PMTiles, DuckDB-WASM, catalog GeoJSON) lives in
`app/` + `data/processed/composite/`. This backend never imports the
preprocess framework; it only *reads* its JSON output.

## Layout

```
backend/app/
  config.py                 env-driven settings (DATABASE_URL, OWNERS_INDEX_PATH, auth knobs)
  db.py                     SQLAlchemy engine/session (SQLite dev default, Postgres via env)
  models.py                 ORM: 11 tables (lead, contact_attempt, owner_cluster_override, antenna_override, task, tenant_setting, user_setting, scoring_preset, app_user, credential, tenant); tenant_id on every data table, credential/tenant are the tenant-determining exceptions
  schemas.py                Pydantic request/response models (the OpenAPI contract)
  lead_status.py            status ladder + transition rules (parity with app/src/lib/lead-status.ts)
  lead_store.py             LeadStore: tenant-scoped CRUD + auto-logged status transitions
  owner_merge_service.py    OwnerMergeService: manual merge/split overrides (display_cluster_id = coalesce(override, raw))
  owners_index_service.py   serves the static index (override-aware) left-joined with the tenant's lead state
  remap_owner_clusters.py   one-time remap of lead state + overrides when the cluster-key recipe changed (ADR-075)
  auth.py                   JWT issue/verify + cookie/bearer extraction + current_principal (also the read-only gate, ADR-077)
  password.py               stdlib PBKDF2-HMAC-SHA256 hashing (no third-party dep; `python -m app.password`)
  credentials.py            the users.txt import format: parse/load + shared auth result types (ADR-069)
  credentials_store.py      the credential table: three-way authenticate, writers, fail-closed boot (ADR-069)
  users.py                  user-management CLI shell (`python -m app.users`, DB-backed)
  demo_seed.py              idempotent seed for the public read-only demo (`python -m app.demo_seed`, ADR-077)
  tenant_service.py         team → tenant resolution, registration order
  login_throttle.py         in-process (ip, username) brute-force throttle (Slice 2)
  auth_service.py           login() (username/password) + user provisioning
  main.py                   FastAPI routes
  *_store.py, *_service.py  per-feature stores and read services (tasks, antennas, settings,
                            scoring presets, users, activity, attention, stats)
backend/tests/              LeadStore + auth + tenant isolation (SQLite default; opt-in testcontainers Postgres)
```

## Schema (tenant-shaped, ADR-055)

`models.py` defines **11 tables** (`tenant_id` on every data table;
`credential` and `tenant` are the deliberate tenant-determining exceptions).
`credential` is documented under **User management** and `user_setting` under
**Per-user settings**. The rest:

- `lead(tenant_id, display_cluster_id, status, notes, contact_name, contact_phone, contact_email, best_channel, created_at, updated_at)`: PK `(tenant_id, display_cluster_id)`. The `contact_*` columns (Slice 3) are the team's **editable** contact record, distinct from the read-only mailing address served from source parcel data.
- `contact_attempt(id, tenant_id, display_cluster_id, occurred_on, channel, outcome, note, direction, logged_by_user_id, created_at)`: manual contact events **and** auto-logged status-transition rows (`channel='status'`) share this one activity stream. `direction` is `outbound` (a touch the team made) or `inbound` (a reply the owner sent, ADR-066); `logged_by_user_id` is the teammate who logged it (nullable for auto-logged rows).
- `tenant(id, name UNIQUE, created_at)`: a **team** (ADR-063). Teams ARE tenants; team isolation is the ADR-055 tenant isolation. Registered find-or-create in credential order, so the first team owns tenant 1 (the pre-teams board). Rows are never deleted.
- `app_user(id, tenant_id, email UNIQUE, display_name, created_at)`: a person who can sign in (email is the username, stored opaquely). Synced to their current team's tenant on every login and request. `display_name` is the friendly name for task assignment, falling back to the email when blank.
- `owner_cluster_override(tenant_id, source_cluster_id, target_cluster_id, created_at)`: manual merge overrides (Slice 7). PK `(tenant_id, source_cluster_id)`. Keyed on **raw** cluster ids, so overrides survive an owners-index recompute (raw ids in the parquet are never mutated).
- `antenna_override(tenant_id, asr, archived, address, owner_*, notes, created_at, updated_at)`: the team's **editable** layer over a single read-only antenna, keyed by its FCC Antenna Structure Registration (ASR) number. It can archive a tower out of Explore, hold a hand-entered address, or capture owner details for an *unowned* tower that has no Lead to hang them on. PK `(tenant_id, asr)`, created lazily on first edit.
- `task(id, tenant_id, title, description, status, priority, due_date, lead_cluster_id, tower_asr, assignee_user_id, labels, source, created_by_user_id, created_at, updated_at, completed_at)`: a unit of work (follow-up, business task, or dev todo), tenant-scoped, optionally linked to a Lead and/or tower (ADR-065).
- `tenant_setting(tenant_id, key, value)`: generic per-tenant config (the auto-follow-up window and its on/off switch). PK `(tenant_id, key)`.
- `scoring_preset(id, tenant_id, name, config, is_default, created_at)`: a named, tenant-shared scoring configuration; `config` is an opaque client-owned JSON blob, at most one `is_default` per tenant (ADR-058 amended).

## Migrations (Alembic)

Schema changes ship as versioned Alembic revisions under
`backend/migrations/versions/`, with sequential rev-ids. The chain is `0001`
(`0001_baseline.py`) → `0002` (`0002_ask_log.py`) → `0003`
(`0003_read_only_credential_drop_ask_log.py`, the head). Revision `0002` added
a table for a since-removed LLM question log, and `0003` drops it.
The convention:

```bash
# 1. Edit app/models.py
# 2. Autogenerate a draft revision (sequential readable rev-ids)
uv run alembic -c backend/alembic.ini revision --autogenerate -m "what changed" --rev-id 0004
# 3. REVIEW the draft: autogenerate never sees data backfills, and SQLite
#    ALTERs run through batch-mode table rebuilds (env.py sets render_as_batch)
# 4. Preview the exact DDL a deploy will run, if in doubt
uv run alembic -c backend/alembic.ini upgrade head --sql
```

`init_db` (called in the app lifespan and by the users CLI) runs
**upgrade-to-head at boot**. On the single-machine, single-writer deploy
(ADR-064) there is no concurrent-migrator hazard, so "did the migration run"
is never a question. If the deploy ever went multi-machine (or Postgres with
multiple writers), the upgrade would need to move out of boot and into a
release step that runs once before the new code starts.

Adoption mechanics: revision `0001` is the baseline autogenerated from the
models at adoption time. A database with tables but no `alembic_version`
(one maintained by the retired additive `init_db` path, whose schema *is* the
baseline) gets **stamped** at `0001`, then upgraded. A fresh database just
runs the chain. Test fixtures stay on fast `create_all` for ephemeral DBs;
`tests/test_migration.py` proves the two paths produce identical schemas
(columns, PKs, indexes, uniques) and that pre-Alembic DDL adopts cleanly. It
runs on SQLite and, via the `MORPHY_TEST_TESTCONTAINERS=1` /
`MORPHY_TEST_DATABASE_URL` opt-ins, on real Postgres.

## Manual owner merge/split (Slice 7, ADR-056)

The conservative cross-state resolver errs toward *not* merging, because a
false merge means calling the wrong person. `OwnerMergeService` is the manual
net: it lets a tenant **merge** two owner clusters or **split** one apart via
the `owner_cluster_override` table. The whole contract is the resolution rule

```
display_cluster_id = coalesce(override_target, raw_cluster_id)
```

`OwnerMergeService.resolve()` follows the override chain (A→B→C) to a fixed
point. The read layer (`OwnersIndexService.effective()`) applies it in **one
place**, so a merge or split shows up identically on every served surface (the
map's tower→landowner resolution, Candidates, My-Leads, counts, the Lead page).
Resolution is never forked per surface. With no overrides (the common case)
the static index is returned untouched.

**Lead-state reconciliation (target wins).** Merge and split write **only** the
override table, never the `lead` or `contact_attempt` tables. A merged owner is
served under the surviving **target** id, and its lead state reconciles across
the member clusters by *target wins*: the target's own row is authoritative for
the scalar fields (status, notes, contact_*), while contact-attempt streams
**concatenate** across all members (so the full contact history stays visible).
Writes resolve the requested id to the target and persist on the target row, so
what you see is what you validate and write. **Split** deletes the source's
override row. Because no lead state ever moved, the source re-emerges with its
own state intact and the target keeps its own, so the operation is fully
reversible. (Consequence: merging adopts the *target's* status, not the
source's; the source's history stays visible in the merged stream and comes
back in full on split. A merge-time "inherit the furthest-along status" seed
was considered and rejected to keep merge and split non-destructive and
reversible.)

## Lead status ladder

```
New ──▶ Researching ──▶ Contacted ──┬──▶ Interested ──▶ In Business
                                    └──▶ Uninterested   (terminal)
```

Default `new`. `uninterested` and `in_business` are terminal; `in_business`
is reachable only via `interested`. Illegal moves (for example
`new → in_business`) are rejected with HTTP 409.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/login` | **username/password → identity-only session JWT** (the front door); sets the `morphy_session` httpOnly cookie (ADR-069) and returns the token in the body for non-browser clients; brute-force throttled |
| POST | `/api/auth/logout` | clear the session cookie, which ends the browser's API *and* `/data` access (ADR-069) |
| GET | `/api/auth/check` | forward-auth seam for the edge `/data/processed/*` gate (ADR-069): cookie/bearer valid and username still credentialed → 204, else 401; no body |
| GET | `/api/auth/me` | the authenticated username, tenant, **team**, and `read_only` flag |
| POST | `/api/auth/demo` | password-less sign-in as the read-only `DEMO_USERNAME` credential; sets the same session cookie as login. 404 unless `DEMO_MODE` is on and that credential exists and is read-only (ADR-077) |
| GET | `/api/auth/config` | public sign-in page config (`{demo_mode}`), which tells the page whether to offer "Explore the demo" |
| GET | `/api/health` | liveness + owners-indexed count (public) |
| GET | `/api/candidates?limit=` | owners at New, ranked by interestingness |
| GET | `/api/my-leads` | owners advanced **off** New: the My-Leads kanban worklist (Slice 5); each carries its status so the client buckets it into a lane |
| GET | `/api/counts` | live nav counts `{candidates, my_leads}` (the index partitions into the two surfaces) |
| GET | `/api/leads/{display_cluster_id}` | full Lead: owner rollup + **holdings** (per-parcel structures + EPSG:4326 footprint) + read-only **mailing address** + tallest tower + lead state + editable contact fields + attempts |
| PUT | `/api/leads/{display_cluster_id}` | set status, notes, and/or contact fields (validates the ladder; a drag on the kanban is just a status PUT) |
| POST | `/api/leads/{display_cluster_id}/attempts` | append a manual contact attempt (date, channel, outcome) |
| POST | `/api/leads/{display_cluster_id}/merge` | merge another owner cluster (`source_cluster_id`) into this Lead; the path id is the survivor (Slice 7) |
| POST | `/api/leads/{display_cluster_id}/split` | split a merged-in cluster (`source_cluster_id`) back out to its own raw cluster |
| POST | `/api/leads/{display_cluster_id}/pursue` | advance a New owner to Researching from Explore and record the triggering antenna (a `channel='flag'` activity row); idempotent (ADR-067) |
| GET · PUT | `/api/antennas/{asr}` | read or edit the tenant's per-antenna override (archive, hand-entered address, unowned-tower owner fields); `GET /api/antennas/archived` lists the archived ASRs |
| GET · POST · PUT · DELETE | `/api/tasks` · `/api/tasks/{task_id}` | Tasks CRUD: follow-ups, business tasks, dev todos, optionally linked to a Lead and/or tower (ADR-065) |
| GET · POST | `/api/attention` · `/api/attention/dismiss` | unhandled inbound replies + overdue tasks (the Dashboard attention feed and nav badge), and per-item dismissal |
| GET · PUT | `/api/settings` | tenant settings (auto-follow-up window and on/off) |
| GET · POST · DELETE | `/api/scoring-presets` · `/api/scoring-presets/{id}` · `/api/scoring-presets/{id}/default` | tenant-shared scoring presets (ADR-058 amended) |
| GET | `/api/stats` | team contact and activity stats over a date, state, or member filter |
| GET | `/api/activity` | the tenant-wide time-ordered activity stream (attempts + status/flag transitions), narrowed by lead, member, channel, or date |
| GET | `/api/users` | the tenant's teammates (for task assignment and member filters) |

(`/api/me`, `/api/me/settings`, and `/api/me/password` are documented in the
**Per-user settings** and **User management** sections below.)

The read half of the full Lead page (holdings, mailing address, tallest tower)
is served from the precomputed **owners index** (schema **v10**,
`scripts/preprocess/owners_index.py`; its module header is the canonical
per-version changelog, and the producer-side contract lives in
[`../scripts/preprocess/CLAUDE.md`](../scripts/preprocess/CLAUDE.md)). The
fields the backend serves, by version:

- **v2** (Slice 3): per-owner `holdings`, `mailing_address`, `tallest_tower_height_m`.
- **v3** (Slice 6): the owner-level filter rollups the shared top-bar
  `FilterModel` reads (`counties`, `active_tower_count`, `structure_count`,
  `structure_types`), surfaced on `OwnerSummary` (`/api/candidates`,
  `/api/my-leads`) and also written to a slim client companion
  `owners_filter.json` (filter and search fields only, no holdings) that the
  map loads to narrow towers.
- **v4** (Slice A): `carriers` (the FCC Universal Licensing System spectrum
  licensees: `{carrier_name, callsign, license_expiry, confidence_tag}`) on
  each tower **structure**.
- **v5** (ADR-067): a per-tower `score` on each structure.
- **v6**: `license_status` and `license_status_desc` on each carrier entry.
- **v7** (ADR-070): `statutory_assessed_value` on each holding.
- **v8** (ADR-073): `carrier_count` on each owner.
- **v9** (ADR-072): `faa_corroborated` on each tower structure.
- **v10** (ADR-075): no new field. The `display_cluster_id` recipe changed from
  name-only to name + state, so every cluster id changed;
  `app/remap_owner_clusters.py` repoints existing lead state and overrides once.

The `Structure` and `OwnerSummary` response models **declare** these fields.
An undeclared field would be silently dropped by `response_model=LeadDetail`,
so it would never reach the Lead page. Only the lead state is per-tenant.
Rebuild both index files after composing states:
`python scripts/preprocess.py --owners-index` (writes `owners_index.json` +
`owners_filter.json`). New `OwnerSummary` / `Structure` fields are
**defaulted**, so a stale index still validates.

Every data route verifies the session JWT: the `morphy_session` httpOnly
cookie first (ADR-069; the SPA's transport), then `Authorization: Bearer`
(tests, curl). It then resolves the tenant by re-checking the **credential
table** on that very request (`current_tenant_id` → `resolve_principal`,
ADR-063 as amended by ADR-069). The store, never the token, decides
authorization. An unauthenticated request, or one whose username no longer
has a credential row, gets **401**. Non-GET routes also pass an
Origin/Referer CSRF check (the cookie transport's backstop; non-browser
clients without those headers pass).

## Generated API contract

The OpenAPI schema FastAPI derives from the routes and Pydantic models is the
**single source of truth for frontend API types**. Two committed, generated
artifacts hang off it:

- `backend/openapi.json`: `python -m scripts.export_openapi` (run from the
  repo root) imports the app object and dumps `app.openapi()` with sorted
  keys. No server boot, no DB, byte-stable across runs.
- `app/src/lib/api-types.ts`: `npm run generate:api` (in `app/`) runs
  `openapi-typescript` over that schema. Types only. The hand-written client
  functions in `leads-api.ts` / `tasks-api.ts` keep their bodies and derive
  their request/response types from `components['schemas']`.

**After any response or request model change, regenerate both and commit
them.** The `api-types` CI workflow re-runs both generators and fails on
`git diff`, and `backend/tests/test_openapi_export.py` fails locally on a
stale schema. This turns the "undeclared response-model field is silently
dropped" gotcha into a compile error: a field that isn't declared never
reaches the schema, so the frontend type doesn't have it and svelte-check
breaks at the use site.

## User management (the `credential` table + CLI, ADR-069)

Credentials live in the app database, in the **`credential`** table
(normalized unique username, self-describing PBKDF2 hash, team, and a
`read_only` flag that defaults to false, ADR-077), which
Litestream replicates with the rest of the DB. **The CLI is the only way to
manage it. Never edit hashes by hand:**

```bash
cd backend
python -m app.users add <username> <team>       # prompts for a password (hidden)
python -m app.users add <username> <team> --read-only   # same, but every write is refused with 403
python -m app.users remove <username>           # locked out on their next request
python -m app.users list                        # usernames + teams only, never hashes
python -m app.users set-password <username>     # prompts; old password stops working
python -m app.users set-team <username> <team>  # moves the user to another team's board
python -m app.users set-read-only <username> on|off  # flips the read-only flag; applies on the next request
python -m app.users import-file <path>          # one-shot users.txt migration (refuses a non-empty table)
```

The CLI writes to the same `DATABASE_URL` the backend serves from (on the Fly
machine, that is the volume DB). **Registration order matters:** the first
credential's team owns tenant 1, the original lead board (`id` order replaced
file order). `import-file` preserves the file's line order for exactly that
reason.

**One runtime endpoint is a sanctioned caller of this writer**
([ADR-068](../docs/adr/0068-self-service-password-change.md), moved onto the
store by ADR-069): `POST /api/me/password {current_password, new_password}`
lets a signed-in user change **their own** password from Settings → Account.
It calls `users.change_password`, which verifies the current password
(constant-time) and rotates the hash through the same store writer the CLI
uses. Team and registration order stay untouched, and the new password works
on the next login attempt. A wrong current password returns 401 and writes
nothing. The username comes from the verified principal, never the body, so a
caller can only rotate their own credential.

## Read-only credentials and the public demo (ADR-077)

**Read-only is a property of a credential**, read from the table on every
request like the team. `current_principal`, the dependency every authenticated
route resolves its caller through, refuses a read-only principal's
non-GET/HEAD/OPTIONS request with **403** and a plain message. There are no
per-route checks, so a new write route is covered automatically, and
`backend/tests/test_read_only_demo.py` enumerates the app's non-GET routes to
prove it. Sign-in, sign-out, and the demo login never resolve a principal, so
they stay open. `POST /api/me/password` is refused like any other write. The
JWT carries no read-only claim.

**`DEMO_MODE`** adds a password-less sign-in for exactly one credential. It is
off unless the env var is explicitly truthy (same parsing as `AUTH_DEV_MODE`).
When on, `POST /api/auth/demo` issues the normal identity-only session cookie
for `DEMO_USERNAME`, after re-checking that the credential exists and is
read-only (404 otherwise). Boot refuses to serve until that credential exists
and is read-only (`ensure_fail_closed_boot`), so the switch can never expose a
writable account. The Origin/Referer check still applies (it is a POST); the
login throttle does not, because there is no password to guess.

**Seeding.** `python -m app.demo_seed` (from `backend/`) creates the demo team
and its read-only credential with a random password printed once and stored
nowhere, then puts six fictional storylines on the demo board over top-scoring
business-entity owners (never individuals). Every note says it is a fictional
demo entry and contact fields stay blank. It is idempotent: an existing
credential is re-flagged read-only with its password untouched, a board that
already has leads is left alone, and a missing owners index skips the leads
but still creates the credential. On Fly, supervisord runs it before uvicorn
whenever `DEMO_MODE` is on.

## Per-user settings (`UserSetting`)

The first *per-user* persisted preference layer (everything before it was
tenant-shaped). `UserSetting` is a generic key/value table keyed
`(tenant_id, user_id, key)`; `UserSettingsStore` mirrors `SettingsStore` with
baked-in defaults, so a user who never opened Settings still reads sane values.
Routes are scoped by **both** ids from the resolved principal:

```
GET  /api/me/settings   → resolved per-user prefs (defaults filled in)
PUT  /api/me/settings   → upsert one or more keys; returns the resolved prefs
PUT  /api/me            → update the signed-in user's display_name
```

Keys: `theme`, `colorblind`, `basemap`, `view_mode`, `home_view`,
`filter_default`, `filter_default_apply`. `home_view` and `filter_default` are
**opaque JSON blobs the client owns**, persisted and served verbatim, never
inspected (the same posture as `ScoringPreset.config`). New prefs slot in as
new keys with no schema change.

## Auth (username/password, ADR-062 + ADR-063 as amended by ADR-069)

The front door is `POST /api/auth/login {username, password}`. Credentials
live in the **`credential` table** (see "User management" above). Usernames and
teams are case-insensitive (trimmed and lowercased); the password is verified
constant-time against a stdlib PBKDF2-HMAC-SHA256 hash (`app/password.py`, no
third-party dependency). A wrong password and an unknown username return
*distinguishable* 401s. That is a deliberate usability-over-enumeration call,
with the enumeration exposure bounded by the throttle. In dev
(`AUTH_DEV_MODE=1`) a built-in `dev`/`dev` credential on a built-in `dev` team
is seeded at boot **through the same store-writer path the CLI uses**, so the
local loop needs zero config and dev can't hide credential-resolution bugs.

On success the route mints an HS256 session JWT that carries **identity only**
(`sub` is the username; no tenant, no team) and sets it in the
**`morphy_session` httpOnly / Secure / SameSite=Lax cookie** (ADR-069). That
cookie is the SPA's transport. Page scripts can never read it, and it rides
automatically on MapLibre, PMTiles, and DuckDB-WASM data fetches, which is
what lets Caddy gate `/data/processed/*` via `forward_auth` →
`GET /api/auth/check`. The body still returns the token for non-browser
clients; `Authorization: Bearer <jwt>` stays accepted, with the cookie
checked first. `POST /api/auth/logout` clears the cookie.
**The credential table is authoritative on every request**: each request
re-checks that the username still has a row and resolves its *current* team,
and that team's tenant scopes the request. Consequences:

- **Removing a user** (`python -m app.users remove`) locks them out on their
  very next request, API *and* data plane. No waiting out the session TTL,
  no restart.
- **Moving a user to another team** (`set-team`) re-homes their live session on
  its next request; the old team's data is untouched.
- Nothing a token carries, even forged extra claims signed with a leaked
  secret, can grant access the store doesn't currently grant.

### Brute-force throttle

`POST /api/auth/login` is guarded by an in-process sliding-window failure
counter (`app/login_throttle.py`) keyed by `(client IP, username)`. After
`AUTH_LOGIN_THROTTLE_MAX` failed attempts within
`AUTH_LOGIN_THROTTLE_WINDOW_SECONDS`, further attempts for that key get **429**
(with a `Retry-After` header). Even a correct password is refused while
blocked. There is **no hard lockout**: the block clears itself as the window
rolls forward, and a successful login resets the key. Because the IP is part
of the key, an attacker who knows a username can't use it to lock a real user
out (no lockout DoS). State is per-process (fine on the single VM; it resets
on restart and is not shared across replicas).

### Posture: fail closed (`AUTH_DEV_MODE`)

A single switch gates the auth posture. It is **off by default** (the safe
production state). With it off, the app **refuses to serve** unless **both**
`AUTH_JWT_SECRET` is set **and** the credential table has at least one row
(`credentials_store.ensure_fail_closed_boot`, run at startup). So a deploy
can be neither open (no secret) nor impossible to log into (no credential).
Set `AUTH_DEV_MODE=1` for the zero-config local loop (ephemeral secret +
built-in `dev`/`dev` login seeded through the same store writer), so the dev
convenience never leaks into a deploy by accident.

#### Revocation and the kill switch

Two operational levers, both immediate (no restart, no extra tooling):

- **Revoke one user:** `python -m app.users remove <username>`. The credential
  table is authoritative on every request, so they are locked out on their
  very next click, even with a valid, unexpired session JWT.
- **Kill every session at once:** rotate `AUTH_JWT_SECRET`. The old secret
  signed every already-issued JWT, so all of them fail verification at once and
  every user must log in again. This is the global panic button for a suspected
  token leak.

Auth environment variables:

| Var | Default | Purpose |
|---|---|---|
| `AUTH_DEV_MODE` | `0` (off) | **master safety switch.** `1` = local dev (ephemeral secret + built-in `dev`/`dev` login). Off ⇒ the prerequisites below are enforced at startup. |
| `AUTH_JWT_SECRET` | _(required off-dev)_ | HS256 signing secret. **Set it from the host secret store on a deploy; never commit it.** Ephemeral per-process value in dev. Rotating it invalidates every active session (kill switch). |
| `AUTH_LOGIN_THROTTLE_MAX` | `5` | failed logins per `(ip, username)` before 429 within the window |
| `AUTH_LOGIN_THROTTLE_WINDOW_SECONDS` | `300` | sliding throttle window (the block clears as it rolls forward; no hard lockout) |
| `DEMO_MODE` | `0` (off) | `1` turns on the password-less read-only demo login (`POST /api/auth/demo`). Boot then also requires the `DEMO_USERNAME` credential to exist and be read-only. |
| `DEMO_USERNAME` | `demo` | the credential the demo login signs in as |
| `AUTH_SESSION_TTL_DAYS` | `30` | session JWT lifetime. Purely a convenience window: authorization is re-checked against the credential table on every request |

### Security model and trade-offs

- **The session rides in an httpOnly cookie** (ADR-069). Page scripts can't
  read it, so an XSS can't exfiltrate the session. CSRF posture: SameSite=Lax
  plus the Origin/Referer middleware on non-GET routes, with no token-dance
  machinery for a same-origin internal tool.
- **Sessions are identity-only; the credential table authorizes every
  request** (ADR-063/069). A leaked token is only as useful as the store
  allows right now. Remove the username and the token is dead on the next
  request, including `/data` fetches, which the edge gates through
  `/api/auth/check`. The 30-day TTL bounds how long an *unrevoked* identity
  stays signed in, nothing more.
- **No `aud`/`iss` claims.** Fine while one secret signs for one audience; add
  them if this secret is ever shared across services.
- **Login throttle is per-process.** The brute-force counter lives in memory on
  one VM; it resets on restart and isn't shared across replicas. That is
  acceptable for a single-VM deployment. A shared store (Redis) would be the
  move for horizontal scaling. (The credential table itself is replica-safe:
  every process reads the same DB.)
- **Deploy checklist.** Set `AUTH_DEV_MODE=0`, set `AUTH_JWT_SECRET` (host
  secret store), and create at least one credential (`python -m app.users add`,
  or `import-file` for a legacy users.txt). The app refuses to serve otherwise.

## Run

```bash
uv sync                                          # .venv from uv.lock; the backend group carries fastapi/sqlalchemy/uvicorn/PyJWT/psycopg
source .venv/bin/activate

# 1. precompute the owners index (reads the composed anchor states on disk)
python scripts/preprocess.py --app-assets         # ensures parcels_attr.parquet exists
python scripts/preprocess.py --owners-index        # writes composite/owners_index.json (+ owners_filter.json)

# 2. run the API (SQLite dev DB at data/processed/lead_state.sqlite3 by default).
#    AUTH_DEV_MODE=1 opts into the local loop; without it the app fails closed
#    (it requires a real AUTH_JWT_SECRET + at least one credential row, see "fail closed").
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
`DATABASE_URL=postgresql+psycopg://user:pass@host/db`. On a deploy, leave
`AUTH_DEV_MODE` off and follow the deploy checklist above (set
`AUTH_JWT_SECRET` from the host secret store and create at least one
credential with `python -m app.users add`). The app refuses to serve
otherwise.

## Test

```bash
source .venv/bin/activate
pytest backend/tests -v          # or just `pytest` (testpaths includes backend/tests)
```

The tests default to **SQLite**. That is fast and reliable, and because
tenant isolation is application-level, SQLite exercises the same behavior.
Opt into real Postgres ([TESTING.md](../docs/TESTING.md), "Backend HTTP API")
either way:

```bash
MORPHY_TEST_DATABASE_URL=postgresql://user:pass@localhost/test pytest backend/tests   # a running Postgres
MORPHY_TEST_TESTCONTAINERS=1 pytest backend/tests                                      # spin one via Docker
```
