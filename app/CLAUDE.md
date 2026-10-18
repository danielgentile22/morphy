# Map app (frontend)

Svelte 5 (runes) + MapLibre + Vite analytical map app, the read-layer triage
surface. Catalog-driven: binds to preprocess output, never to a hardcoded state.
Does NOT own write state (Lead status/notes/attempts live in `backend/`) or any
data production (that's `scripts/preprocess/`).

**Deep dive:** [`app/ARCHITECTURE.md`](ARCHITECTURE.md). Read it before non-trivial changes.

## Entry points
- `src/App.svelte`, `src/main.ts`: app shell + boot.
- `src/lib/filter-model.ts` is the deep module: one `FILTER_FIELDS` registry →
  `composeOwnerWhere()` (SQL string, unit-tested byte-for-byte) + `matchesOwner()`
  (runtime predicate). Both Explore lenses (the map's tower layer and Explore's
  ranked tower list) narrow by it. (Leads sorts by score, not this filter.)
- `src/lib/schema.ts` pins the v3 composite field names (the data contract).
- `src/lib/*.svelte.ts`: runes stores (auth, leads, filter-model, stores).
- `src/lib/leads-api.ts` (auth via `auth-store.svelte.ts` → `login`/`logout`/`fetchMe`),
  `tasks-api.ts`, `activity-store.svelte.ts`, `user-settings-store.svelte.ts` are the
  bridges to `backend/` (everything that calls `/api`).
- `src/lib/notice.svelte.ts` + `components/Notice.svelte`: one app-wide transient
  notice. `leads-api.ts` raises it on any 403, so a refused write shows one calm
  message instead of a broken panel.

## Contracts & invariants
- **Schema-completeness is enforced**: `tests/unit/schema-completeness.test.ts`
  fails CI if a compose renames/drops a field. When the composite schema changes,
  update `schema.ts` (+ `TOWER_SCHEMA` for tower fields). Don't paper over drift.
- **The map is structures-first**: a tower click resolves to its landowner;
  don't reintroduce the retired parcel-centric sidebar.
- `carriers` is a list-of-struct, special-cased via `parseCarriers` + the shared
  `CarrierList.svelte` on both tower surfaces. An empty carrier list is the common
  case (~6-17% coverage). Render the empty state; don't treat it as an error.
- Filter logic lives in `filter-model.ts` only; don't fork it per Explore lens.
- **`src/lib/api-types.ts` is generated. Never hand-edit it.** It is produced
  from `backend/openapi.json` by `npm run generate:api`, and the API clients derive
  their types from its `components['schemas']`. Backend model changed? Regenerate
  both artifacts (mechanics in `backend/CLAUDE.md`). The `api-types` CI workflow
  fails on drift.
- **The MapTiler key is optional and never committed.** `VITE_MAPTILER_KEY` comes
  from the git-ignored `app/.env` (documented by `app/.env.example`) in dev, and
  from `deploy.sh` as a Docker build arg. `src/lib/basemap.ts` gates Satellite on
  `maptilerEnabled`; with no key, Satellite is hidden and degrades to keyless Esri
  Dark Gray. Keep that fallback, because a fresh clone and CI both build
  without a key.

- **The read-only demo is enforced by the backend, reflected here** (ADR-077).
  `auth.readOnly` (from `/api/auth/me`'s `read_only`) hides or disables write
  controls and shows the "Read-only demo" badge in the user menu;
  `auth.demoMode` (from the public `GET /api/auth/config`) decides whether
  `SignIn.svelte` offers "Explore the demo" (`POST /api/auth/demo`). Appearance
  prefs apply locally for a read-only visitor with no server write. Hiding a
  control is UX only: never treat it as the security boundary, and gate any new
  write control on `auth.readOnly`.

## Patterns
- New filter field: add to the `FILTER_FIELDS` registry. Both the SQL projection
  and the predicate fall out of it. Add the byte-for-byte SQL assertion.
- New composite field surfaced in UI: add to `schema.ts` first, then render.

## Run
`cd app && npm run dev` → http://localhost:5173. `npm run test:unit` (Vitest),
`npm run test:e2e` (Playwright; the e2e suite was stale when the project was
archived).

## Related context
- Write-layer API it calls: [`../backend/CLAUDE.md`](../backend/CLAUDE.md)
- Where its data comes from: [`../scripts/preprocess/CLAUDE.md`](../scripts/preprocess/CLAUDE.md)
