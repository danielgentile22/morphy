# morphy design gallery

A component library that syncs to Claude Design. **This is the parked light "Linen"
reference**: warm-paper neutrals with a pine-teal accent, kept for exploration and *not*
a mirror of the shipped app. The shipped chrome is the dark "Halo" re-skin, whose source
of truth is **`app/src/system.css`** (aliased onto the app's tokens in
`app/src/app.css`). `tokens.css` here still holds the Linen palette, so previews render
in Linen, not in the Halo look.

## Layout

- `tokens.css` holds color, type, radius and shadow tokens (light, dark, colorblind).
- `base.css` holds shared primitives (`.chip`, `.set-*`, `.pill`, panel header).
- `components/*.html` holds one `@dsCard`-tagged preview per primitive or surface.

## Sync to claude.ai/design

The `DesignSync` tool syncs the gallery: `create_project` → review plan →
`finalize_plan` → `write_files`. Linen explorations happen here. To change the Halo
look, edit `app/src/system.css` directly; `app/src/app.css` only aliases onto it.

## Out of scope

Map data-encoding colors (`app/src/lib/palette.ts`) are locked for accessibility and are
**not** tokens. Leave them alone when restyling.
