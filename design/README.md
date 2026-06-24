# Morphy Consulting — design gallery

A Claude Design–syncable component library. **This is the parked light "Linen"
reference** — warm-paper neutrals + a pine-teal accent — kept as an exploration
surface, *not* a mirror of the live app. The shipped chrome is the dark "Halo"
facelift, whose source of truth is **`app/src/system.css`** (aliased onto the
app's tokens in `app/src/app.css`). `tokens.css` here still holds the Linen
palette, so previews render in Linen, not in the live Halo look.

## Layout

- `tokens.css` — color / type / radius / shadow tokens (light, dark, cb)
- `base.css` — shared primitives (`.chip`, `.set-*`, `.pill`, panel header)
- `components/*.html` — one `@dsCard`-tagged preview per primitive/surface

## Sync to claude.ai/design

`/design-login` is already done. Then run the **`/design-sync`** skill, which
drives the `DesignSync` tool: `create_project` → review plan → `finalize_plan`
→ `write_files`. Iterate Linen explorations here. To change the *live* (Halo)
look, edit `app/src/system.css` directly — `app/src/app.css` only aliases onto
it. (The Qt puller needs a tokens→QSS translation, not direct reuse, and is
frozen — PRD #138.)

## Out of scope

Map data-encoding colors (`app/src/lib/palette.ts`) are accessibility-locked
and are **not** tokens — don't touch them in the facelift.
