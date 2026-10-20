# Lead-triage write layer (backend)

A tenant-shaped FastAPI + SQLAlchemy service that holds the **write layer**
(Lead status, notes, contact attempts) on top of the static, read-only owners
index that the preprocess pipeline precomputes. It only *reads* that JSON
output and never imports the preprocess framework.

**Deep dive:** [`backend/README.md`](README.md). Read it before changing auth,
the schema, or the owners-index read path.

## Entry points
- `app/main.py`: FastAPI routes.
- `app/lead_store.py`: tenant-scoped CRUD plus auto-logged status transitions.
- `app/owners_index_service.py`: serves the static index, override-aware,
  left-joined with the tenant's lead state.
- `app/credentials_store.py` + `app/users.py`: the `credential` table (the only
  credential source, ADR-069) and its management CLI (`python -m app.users`).
- `app/auth_service.py`, `app/auth.py`, `app/tenant_service.py`: login, JWT
  (cookie or bearer), team to tenant. `auth.current_principal` is also the
  read-only gate.
- `app/demo_seed.py`: idempotent seed for the public read-only demo
  (`python -m app.demo_seed`, [ADR-077](../docs/adr/0077-read-only-demo-credential.md)).
  Creates the demo team and read-only credential and puts fictional leads on its
  board over government owners only (ADR-078).

## Contracts and invariants (do not relax: ADR-062/063/069/077)
- **`tenant_id` on every table; every route filters by it.** No `tenant_id=1` stub.
  The `credential` table is the deliberate exception alongside `tenant` itself,
  because a credential *determines* the tenant.
- **The `credential` table is the only credential source and re-authorizes every
  request**: API routes *and* the edge `/data` gate (`/api/auth/check` behind
  Caddy `forward_auth`). Removing or re-teaming a user applies on their next
  click. Manage it only via `python -m app.users`; never hand-edit hashes; never
  commit the DB or a legacy `users.txt` (the commit-guard test enforces both).
  - **One sanctioned runtime caller** ([ADR-068](../docs/adr/0068-self-service-password-change.md)):
    `POST /api/me/password` rotates the *caller's own* hash via
    `users.change_password`, which calls the store's password writer
    (verify, then write). The username comes from the verified principal,
    never the request body.
- **The session rides in the `morphy_session` httpOnly cookie** (ADR-069),
  checked before the bearer header. Never move the token back to localStorage or
  weaken the cookie attributes; keep the Origin/Referer middleware on non-GET routes.
- **Per-user settings (`UserSetting`)** are scoped by **both** `tenant_id`
  *and* `user_id` (PK `(tenant_id, user_id, key)`); `UserSettingsStore` mirrors
  `SettingsStore`. `home_view` and `filter_default` are opaque client-owned JSON
  blobs: persist and serve them verbatim, never inspect them (like
  `ScoringPreset.config`).
- **JWT is identity-only.** Never put tenant, team, or read-only claims in it.
- **Read-only is a `credential.read_only` flag with one gate** (ADR-077).
  `current_principal` refuses a read-only principal's non-GET/HEAD/OPTIONS
  request with 403, so every authenticated write route is covered with no
  per-route check. Do not add per-route checks or a bypass. A test enumerates
  every non-GET route and asserts 403 for a read-only principal.
- **`DEMO_MODE` fails closed.** Off unless explicitly truthy. When on,
  `ensure_fail_closed_boot` refuses to start unless the `DEMO_USERNAME`
  credential exists and is read-only, and `POST /api/auth/demo` re-checks both
  on every call (404 otherwise), so it can never issue a writable session.
- **Teams ARE tenants**, registered in credential order (the first registered
  team owns tenant 1 and the pre-teams board; `import-file` preserves a legacy
  file's order). Tenant rows are never deleted.
- **Never reintroduce** magic-link auth, `APP_USERS`, or `APP_USERS_FILE`. Keep
  `AUTH_DEV_MODE` fail-closed (enforced at startup by `ensure_fail_closed_boot`:
  outside dev mode the app needs a real secret and at least one credential row).
- **Owner merge/split resolves in one place**: `display_cluster_id =
  coalesce(override_target, raw_cluster_id)` in `OwnersIndexService.effective`.
  Never fork resolution per surface; never bake an override into the parquet
  (raw cluster ids stay untouched so overrides survive a recompute).
- **The owners index is schema-versioned (currently v10).** Declare any new
  `Structure`/`OwnerSummary` field on the backend model, because `response_model`
  silently drops undeclared fields. The producer-side versioning contract
  (bump, safe defaults, version history) lives in
  [`../scripts/preprocess/CLAUDE.md`](../scripts/preprocess/CLAUDE.md).
- **Schema changes ship as Alembic revisions.** Edit `app/models.py`,
  then `uv run alembic -c backend/alembic.ini revision --autogenerate -m "..."
  --rev-id 000N` and *review the output*. Autogenerate cannot see data
  backfills, and SQLite ALTERs run through batch mode (env.py sets
  `render_as_batch`). `init_db` upgrades to head at app boot (safe with one
  machine and one writer); a pre-Alembic DB is stamped at the `0001` baseline.
  The current head is revision `0003`
  (`migrations/versions/0003_read_only_credential_drop_ask_log.py`).
  Never reintroduce additive column/index back-fill helpers in `db.py`; test
  fixtures keep fast `create_all`, and `tests/test_migration.py` proves the
  two paths build identical schemas.
- **The OpenAPI schema is the frontend's type contract.** After any
  request/response model change, regenerate and commit both generated artifacts:
  `uv run python -m scripts.export_openapi` (writes `backend/openapi.json`) and
  `cd app && npm run generate:api` (writes `app/src/lib/api-types.ts`). The
  `api-types` CI workflow fails on drift; `tests/test_openapi_export.py` fails
  locally on a stale schema. Declare every response field on the model. An
  undeclared field is dropped from responses *and* missing from the generated types.

## CI gate
`ruff check .` + `ruff format --check .`, **`uv run pyright`** (basic-mode type
check, scoped to `backend/` only, config in `[tool.pyright]`), the full pytest
suite, and the `api-types` drift gate (the regenerated schema and types must
match the committed artifacts) all run on every push. Run the matching checks
before declaring backend work done. The pyright gate sits at **zero**
diagnostics. Fix type errors at the source. Reach for a targeted, commented
`# pyright: ignore[...]` only when a diagnostic is genuinely unfixable (for
example a third-party stub gap), never a global rule relaxation. The scripts,
pipeline, and puller are deliberately out of scope, so do not widen `include`.

## Related context
- The index it reads: [`../scripts/preprocess/CLAUDE.md`](../scripts/preprocess/CLAUDE.md)
- The frontend that calls it: [`../app/CLAUDE.md`](../app/CLAUDE.md)
