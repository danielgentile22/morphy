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
- `app/credentials_store.py` + `app/users.py` — the `credential` table (the only
  credential source, ADR-069) + its management CLI (`python -m app.users`).
- `app/auth_service.py`, `app/auth.py`, `app/tenant_service.py` — login, JWT
  (cookie or bearer), team→tenant.

## Contracts & invariants (do not relax — PRD #75/#83/#130, ADR-062/063/069)
- **`tenant_id` on every table; every route filters by it.** No `tenant_id=1` stub.
  (The `credential` table is the deliberate exception alongside `tenant` itself —
  a credential *determines* the tenant.)
- **The `credential` table is the only credential source and re-authorizes every
  request** — API routes *and* the edge `/data` gate (`/api/auth/check` behind
  Caddy `forward_auth`). Removal / re-teaming applies on the next click. Manage it
  only via `python -m app.users`; never hand-edit hashes; never commit the DB or a
  legacy `users.txt` (the commit-guard test enforces both).
  - **One sanctioned runtime caller** (PRD #121, [ADR-068](../docs/adr/0068-self-service-password-change.md)):
    `POST /api/me/password` rotates the *caller's own* hash via
    `users.change_password` → the store's password writer (verify-then-write).
    The username comes from the verified principal, never the request body.
- **The session rides in the `pilot_session` httpOnly cookie** (ADR-069), checked
  before the bearer header. Never move the token back to localStorage or weaken
  the cookie attributes; keep the Origin/Referer middleware on non-GET routes.
- **Per-user settings (`UserSetting`, PRD #121)** are scoped by **both** `tenant_id`
  *and* `user_id` (PK `(tenant_id, user_id, key)`); `UserSettingsStore` mirrors
  `SettingsStore`. `home_view` / `filter_default` are opaque client-owned JSON
  blobs — persist + serve verbatim, never inspect (like `ScoringPreset.config`).
- **JWT is identity-only.** Never put tenant/team claims back in it.
- **Teams ARE tenants**, registered in credential order (first registered team owns
  tenant 1 + the pre-teams board; `import-file` preserves a legacy file's order).
  Tenant rows are never deleted.
- **Never reintroduce** magic-link auth, `APP_USERS`, or `APP_USERS_FILE`. Keep
  `AUTH_DEV_MODE` fail-closed (enforced at startup by `ensure_fail_closed_boot`:
  real secret + ≥1 credential row outside dev).
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
