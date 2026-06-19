# audit-site — data-audit results browser

A standalone Svelte 5 + Vite app for browsing the **data audit**
(`docs/research/data-audit/`): 20 cards, 67 signals (each with five
controlled-vocab trust tags + a verdict + a dossier deep-link), the
verification log, the forward/backward reconciliation, and the framework spec.

It is **data-driven** — it reads `index.json` + the dossier markdown at runtime
and renders them. A re-run of any audit card rewrites those files, so the site
**auto-populates on a refresh** with no code change and no rebuild in dev.

## Run it

```bash
cd audit-site
npm install          # once
npm run dev          # → http://localhost:5273/audit/
```

The dev server serves the live audit artifacts from `docs/research/data-audit/`
at `/audit/data/*` (a small Vite plugin, `vite/serve-audit-data.ts`), re-reading
disk on every request — so re-running a card and refreshing the page shows the
new data immediately.

Other commands:

```bash
npm run check        # svelte-check (type + a11y)
npm run test:unit    # vitest — pure logic (routing, filters, markdown anchors)
npm run build        # svelte-check && vite build → dist/  (base-pathed /audit/)
npm run preview      # serve the built bundle → http://localhost:4273/audit/
```

## How it's wired

- **`index.json` is the single source of truth.** `src/lib/audit-data.ts`
  fetches it once at boot; `vocab` drives every filter/legend; nothing is
  hardcoded. Dossier `.md` files are fetched on demand.
- **Signal → dossier deep-links.** A signal's `dossier` field
  (`fcc-asr.md#tower_coords`) points at an anchor that is the **signal id in the
  backticks** of the `## Signal: \`id\`` heading — *not* GitHub's slug of the
  whole heading. `src/lib/markdown.ts` emits matching `id=`s and rewrites
  cross-`.md` / in-page links onto the app's hash router so the boards navigate
  inside the SPA.
- **Per-state signals.** Ids carry a `@NN` FIPS suffix (`owner_name@12` = FL);
  the state filter is *derived* from the suffix, and the per-state dossier
  heading keys on the **base** id (`owner_name`), which the detail view extracts.
- **Cards with no signals** (T-00 / T-21 / T-30 / T-90 / T-91) are handled —
  the signal views never assume ≥1 signal.

### Routes (hash-based)

`#/` overview · `#/signals[?…filters]` browser · `#/signals/<id>` detail ·
`#/cards` · `#/cards/<id>` · `#/doc/<file>[/<anchor>]` any board/dossier.
The Signals browser's filter state lives in the query string (shareable links).

## Deployment (behind the existing auth)

The app is base-pathed at `/audit/` and ships inside the production image. The
`Dockerfile` builds it (stage `audit-frontend`) and bakes the audit artifacts in
at `/srv/audit-data`; the `Caddyfile` serves `/audit/*` and `/audit/data/*`
behind the **same `forward_auth → /api/auth/check` session gate** as
`/data/processed/*` — so it's reachable only by a signed-in user, never public.
A re-run that rewrites `docs/research/data-audit/` ships on the next
`./deploy.sh code`. Edge behaviour is covered by `tests/test_caddy_serving.py`.
