/**
 * Parcel layer zoom + opacity — the single tunable source of truth for *when*
 * and *how crisply* parcels appear on the map (PRD #163 / #165).
 *
 * The pre-#165 behaviour was a size-graduated fade-in: big rural parcels showed
 * first, small urban ones filled in as you kept zooming. That was tippecanoe's
 * `--drop-densest-as-needed` shedding the densest (small, urban) parcels at low
 * zoom to keep each tile under budget — the low-zoom tiles are *incomplete*.
 *
 * Fix: render the parcel fill + line layers only at/above a single appearance
 * zoom `Z_ON`, where the full parcel set already fits per tile, so parcels
 * appear **together** rather than by size. Below `Z_ON` MapLibre never requests
 * the incomplete low-zoom tiles at all (so this is performance-neutral-to-
 * positive), and individual parcels are invisible noise at state scale anyway.
 *
 * Keep these expressions pure and in one place so the appearance zoom is one
 * tunable constant. The companion tile slice (#167) raises tippecanoe's `-Z`
 * (`MIN_ZOOM` in `scripts/preprocess/tiles.py`) to this same value — the
 * frontend `Z_ON` and the tile min-zoom must never drift.
 */

import type { ExpressionSpecification } from 'maplibre-gl';

/**
 * The appearance zoom: parcels are not rendered below it, and the full set is
 * present at/above it.
 *
 * Empirically tuned (PR #165), starting at z11 per the PRD: zoomed into the
 * densest FL metro (Hialeah / Miami-Dade) and counted distinct parcels rendered
 * in a fixed ~0.9 km² ground window as the map zoomed in — the zoom where that
 * count stops growing is where tippecanoe stops dropping. Measured counts:
 *
 *   z11 → 5 · z12 → 192 (26%) · z13 → 523 (72%) · z14 → 731 (100%, plateau)
 *
 * The set is only fully complete at z14 — which is also the tile `MAX_ZOOM`, so
 * the densest blocks reach completeness only at the deepest tile. Pinned at 14
 * so parcels are *always 100% present* the instant they appear (the strict
 * "no size-graduated fade-in" reading of the acceptance bar); a lower value
 * would leave a residual fill-in in those densest blocks. Genuinely lowering
 * `Z_ON` is a tile-budget question (raise `MAX_ZOOM` / relax `--drop-densest`),
 * tracked tile-side — out of scope for this frontend-only slice.
 */
export const Z_ON = 14;

/**
 * Width of the crisp pop-in ramp above `Z_ON`, in zoom levels. A tight
 * `Z_ON → Z_ON + FADE` fade (rather than a hard binary flash) softens the
 * appearance without reintroducing a by-size bleed-in.
 */
const FADE = 0.5;

/** Opacity of an unselected parcel fill once fully on. */
const FILL_OPACITY = 0.55;
/** Opacity of the selected parcel fill (brightened to read as highlighted). */
const FILL_OPACITY_SELECTED = 0.85;
/** Opacity of the parcel outline once fully on. */
const LINE_OPACITY = 0.85;

export interface ParcelLayerAppearance {
  /** Layer `minzoom`: parcels are not rendered below `Z_ON`. */
  minzoom: number;
  /**
   * `fill-opacity` paint expression. The selected-parcel brightening is the
   * interpolation's *output* stop — `zoom` must stay the top-level interpolate
   * input, so the `case` can't wrap it. Filtering never fades parcels (#119):
   * they are stable context while the filter narrows towers.
   */
  fillOpacity: ExpressionSpecification;
  /** `line-opacity` paint expression (same crisp ramp as the fill). */
  lineOpacity: ExpressionSpecification;
}

/**
 * Pure builder for the parcel fill/line zoom + opacity expressions, keyed off a
 * single appearance zoom. Crisp on at `zOn` with a tight `zOn → zOn + FADE`
 * ramp so parcels pop in together instead of bleeding in by size.
 */
export function parcelLayerAppearance(zOn: number = Z_ON): ParcelLayerAppearance {
  return {
    minzoom: zOn,
    fillOpacity: [
      'interpolate',
      ['linear'],
      ['zoom'],
      zOn,
      0,
      zOn + FADE,
      ['case', ['boolean', ['feature-state', 'selected'], false], FILL_OPACITY_SELECTED, FILL_OPACITY],
    ],
    lineOpacity: ['interpolate', ['linear'], ['zoom'], zOn, 0, zOn + FADE, LINE_OPACITY],
  };
}
