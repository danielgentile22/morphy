# Map app (frontend)

Svelte 5 (runes) + MapLibre + Vite analytical map app — the read-layer triage
surface. Catalog-driven: binds to preprocess output, never to a hardcoded state.
Does NOT own write state (Lead status/notes/attempts live in `backend/`) or any
data production (that's `scripts/preprocess/`).

**Deep dive:** [`app/ARCHITECTURE.md`](ARCHITECTURE.md) — read it before non-trivial changes.

## Entry points
- `src/App.svelte`, `src/main.ts` — app shell + boot.
- `src/lib/filter-model.ts` — the deep module: one `FILTER_FIELDS` registry →
  `composeOwnerWhere()` (SQL string, unit-tested byte-for-byte) + `matchesOwner()`
  (runtime predicate). Both the map's tower layer and the Candidates list read it.
- `src/lib/schema.ts` — pins the v3 composite field names (the data contract).
- `src/lib/*.svelte.ts` — runes stores (auth, leads, filter-model, stores).
- `src/lib/leads-api.ts`, `auth-token.ts` — the only bridge to `backend/`.

## Contracts & invariants
- **Schema-completeness is enforced**: `tests/unit/schema-completeness.test.ts`
  fails CI if a compose renames/drops a field. When the composite schema changes,
  update `schema.ts` (+ `TOWER_SCHEMA` for tower fields) — don't paper over drift.
- **The map is structures-first** (#50): a tower click resolves to its landowner;
  don't reintroduce the retired parcel-centric sidebar.
- `carriers` is a list-of-struct, special-cased via `parseCarriers` + the shared
  `CarrierList.svelte` on both tower surfaces. An empty carrier list is the common
  case (~6–17% coverage) — render the empty state, don't treat it as an error.
- Filter logic lives in `filter-model.ts` only; don't fork per-surface filtering.

## Patterns
- New filter field: add to the `FILTER_FIELDS` registry — both the SQL projection
  and the predicate fall out of it. Add the byte-for-byte SQL assertion.
- New composite field surfaced in UI: add to `schema.ts` first, then render.

## Run
`cd app && npm run dev` → http://localhost:5173. `npm run test:unit` (Vitest),
`npm run test:e2e` (Playwright; the e2e suite is currently stale — issue #92).

## Related context
- Write-layer API it calls: [`../backend/AGENTS.md`](../backend/AGENTS.md)
- Where its data comes from: [`../scripts/preprocess/AGENTS.md`](../scripts/preprocess/AGENTS.md)
