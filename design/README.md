# Morphy Consulting — design gallery

The current look of the app, extracted as a Claude Design–syncable component
library. **`tokens.css` is the single source of truth** — it mirrors
`app/src/app.css` `:root` (+ dark + colorblind). Every preview paints through
it, so the gallery renders identically to the live app.

## Layout

- `tokens.css` — color / type / radius / shadow tokens (light, dark, cb)
- `base.css` — shared primitives (`.chip`, `.set-*`, `.pill`, panel header)
- `components/*.html` — one `@dsCard`-tagged preview per primitive/surface

## Sync to claude.ai/design

`/design-login` is already done. Then run the **`/design-sync`** skill, which
drives the `DesignSync` tool: `create_project` → review plan → `finalize_plan`
→ `write_files`. Iterate the facelift there; pull refined `tokens.css` back and
re-apply to `app/src/app.css`, then propagate to `audit-site/` and the landing
page. (The Qt puller needs a tokens→QSS translation, not direct reuse, and is
frozen — PRD #138.)

## Out of scope

Map data-encoding colors (`app/src/lib/palette.ts`) are accessibility-locked
and are **not** tokens — don't touch them in the facelift.
