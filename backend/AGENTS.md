# Lead-triage write-layer (backend)

Tenant-shaped FastAPI + SQLAlchemy service holding the **write layer** — Lead
status, notes, contact attempts — on top of the static, read-only owners index
the preprocess pipeline precomputes. It only *reads* that JSON output; it never
imports the preprocess framework.

**Deep dive:** [`backend/README.md`](README.md) — read it before changing auth,
the schema, or the owners-index read path.

## Entry points
- `app/main.py` — FastAPI routes.
- `app/lead_store.py` — tenant-scoped CRUD + auto-logged status transitions.
- `app/owners_index_service.py` — serves the static index, override-aware,
  left-joined with the tenant's lead state.
- `app/credentials.py` + `app/users.py` — the `users.txt` credential source + its
  management CLI (`python -m app.users`).
- `app/auth_service.py`, `app/auth.py`, `app/tenant_service.py` — login, JWT, team→tenant.

## Contracts & invariants (do not relax — PRD #75/#83, ADR-062/063)
- **`tenant_id` on every table; every route filters by it.** No `tenant_id=1` stub.
- **`backend/users.txt` (`username:hash:team`) is the only credential source and
  re-authorizes every request** (mtime-cached). Removal / re-teaming applies on
  the next click. Manage it only via `python -m app.users`; never hand-edit hashes,
  never commit the real file (a commit-guard test enforces this).
  - **One sanctioned runtime caller** (PRD #121, [ADR-068](../docs/adr/0068-self-service-password-change.md)):
    `POST /api/me/password` rotates the *caller's own* hash via
    `users.change_password` → `users.set_password` (verify-then-atomic-write). It
    calls the `app.users` API — it does **not** hand-edit hashes — so the invariant
    holds. The username comes from the verified principal, never the request body.
    Prod caveat: `users.txt` is on the Fly volume, **not** Litestream-replicated
    like the DB.
- **Per-user settings (`UserSetting`, PRD #121)** are scoped by **both** `tenant_id`
  *and* `user_id` (PK `(tenant_id, user_id, key)`); `UserSettingsStore` mirrors
  `SettingsStore`. `home_view` / `filter_default` are opaque client-owned JSON
  blobs — persist + serve verbatim, never inspect (like `ScoringPreset.config`).
- **JWT is identity-only.** Never put tenant/team claims back in it.
- **Teams ARE tenants**, registered in file order (first team owns tenant 1 + the
  pre-teams board). Tenant rows are never deleted.
- **Never reintroduce** magic-link auth or `APP_USERS`. Keep `AUTH_DEV_MODE`
  fail-closed.
- **Owner merge/split resolves in one place**: `display_cluster_id =
  coalesce(override_target, raw_cluster_id)` in `OwnersIndexService.effective`.
  Never fork resolution per surface; never bake an override into the parquet
  (raw cluster ids stay untouched so overrides survive a recompute).
- **Owners index is schema v4.** Extending it: bump `OWNERS_INDEX_SCHEMA_VERSION`,
  give new fields safe defaults (a stale index must still serve), and declare any
  new `Structure`/`OwnerSummary` field on the backend model (undeclared fields are
  silently dropped by `response_model`).
- Schema changes ride the additive `init_db` migration (`db._migrate_added_columns`)
  until Alembic.

## CI gate
`ruff check .` + `ruff format --check .` is the real gate — run both before
declaring backend work done (pytest CI job is a placeholder).

## Related context
- The index it reads: [`../scripts/preprocess/AGENTS.md`](../scripts/preprocess/AGENTS.md)
- The frontend that calls it: [`../app/AGENTS.md`](../app/AGENTS.md)
