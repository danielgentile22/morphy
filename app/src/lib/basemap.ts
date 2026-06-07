/**
 * Basemap + initial-view helpers (PRD #121) — pure, so they unit-test cleanly
 * (the live MapLibre map is e2e territory).
 *
 * The three offered basemaps are all keyless Carto raster tilesets, under the
 * license already accepted for the current Positron basemap — no API key, in
 * keeping with the no-backend basemap constraint:
 *   - `light`   → Positron   (`light_all`)
 *   - `voyager` → Voyager    (`voyager`)
 *   - `dark`    → Dark Matter (`dark_all`)
 */

import type { StyleSpecification } from 'maplibre-gl';

import type { EffectiveTheme } from './appearance';

export type BasemapName = 'light' | 'voyager' | 'dark';

/** Carto tileset slug per basemap choice (the keyless raster CDN). */
const CARTO_TILESET: Record<BasemapName, string> = {
  light: 'light_all',
  voyager: 'voyager',
  dark: 'dark_all',
};

const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> ' +
  'contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

/** Which tileset actually paints. The dark theme nudges the *default* light
 *  basemap to Dark Matter so a bright map doesn't glare inside a dark UI; an
 *  explicit Voyager/Dark choice is honoured as-is (overridable). */
export function resolveBasemapName(name: BasemapName, theme: EffectiveTheme): BasemapName {
  if (theme === 'dark' && name === 'light') return 'dark';
  return name;
}

/** The raster tile URLs for a basemap choice (theme-aware). Exposed on its own
 *  so a mounted map can hot-swap just the basemap source's tiles
 *  (`RasterTileSource.setTiles`) without a full `setStyle` that would drop the
 *  app's tower/parcel/solar layers. */
export function basemapTiles(name: BasemapName, theme: EffectiveTheme): string[] {
  const tileset = CARTO_TILESET[resolveBasemapName(name, theme)];
  return ['a', 'b', 'c'].map(
    (s) => `https://${s}.basemaps.cartocdn.com/${tileset}/{z}/{x}/{y}.png`,
  );
}

/** A MapLibre style for the chosen basemap, theme-aware (see resolveBasemapName). */
export function basemapStyle(name: BasemapName, theme: EffectiveTheme): StyleSpecification {
  return {
    version: 8,
    sources: {
      basemap: {
        type: 'raster',
        tiles: basemapTiles(name, theme),
        tileSize: 256,
        attribution: ATTRIBUTION,
      },
    },
    layers: [{ id: 'basemap', type: 'raster', source: 'basemap' }],
  };
}

/** A map camera position — the opaque `home_view` blob and the persisted
 *  last-position both serialise to this shape. */
export interface MapView {
  lng: number;
  lat: number;
  zoom: number;
}

export interface ViewPrefs {
  viewMode: 'home' | 'last';
  home: MapView | null;
}

/** The camera the map should open on, or `null` to use the app's default view
 *  (the anchor-state bounds). Home wins when pinned and selected; otherwise the
 *  last position I left off at; otherwise the default. */
export function resolveInitialView(prefs: ViewPrefs, lastSaved: MapView | null): MapView | null {
  if (prefs.viewMode === 'home' && prefs.home) return prefs.home;
  return lastSaved;
}

/** Parse a stored `home_view` / last-position JSON blob into a MapView, or null
 *  when empty/malformed (a fresh user, or a bad cache). */
export function parseMapView(json: string): MapView | null {
  if (!json) return null;
  try {
    const v: unknown = JSON.parse(json);
    if (v && typeof v === 'object') {
      const o = v as Record<string, unknown>;
      if (
        typeof o.lng === 'number' &&
        typeof o.lat === 'number' &&
        typeof o.zoom === 'number' &&
        Number.isFinite(o.lng) &&
        Number.isFinite(o.lat) &&
        Number.isFinite(o.zoom)
      ) {
        return { lng: o.lng, lat: o.lat, zoom: o.zoom };
      }
    }
  } catch {
    // malformed — treat as unset
  }
  return null;
}
