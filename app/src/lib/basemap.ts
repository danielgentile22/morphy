/**
 * Basemap + initial-view helpers (PRD #121) — pure, so they unit-test cleanly
 * (the live MapLibre map is e2e territory).
 *
 * Three keyless Carto raster basemaps, plus an optional MapTiler Satellite
 * Hybrid (imagery + baked labels) gated on a client-side key:
 *   - `light`     → Positron    (`light_all`)
 *   - `voyager`   → Voyager     (`voyager`)
 *   - `dark`      → Dark Matter (`dark_all`)
 *   - `satellite` → MapTiler Satellite Hybrid (needs `VITE_MAPTILER_KEY`)
 */

import type { RasterSourceSpecification, StyleSpecification } from 'maplibre-gl';

export type BasemapName = 'light' | 'voyager' | 'dark' | 'satellite';

/** The keyless Carto raster basemaps. */
type CartoBasemap = 'light' | 'voyager' | 'dark';

/** Carto tileset slug per basemap choice (the keyless raster CDN). */
const CARTO_TILESET: Record<CartoBasemap, string> = {
  light: 'light_all',
  voyager: 'voyager',
  dark: 'dark_all',
};

const CARTO_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> ' +
  'contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

/** MapTiler key (client-side, referrer-restricted). Absent → Satellite is
 *  hidden in settings and any stored `satellite` pref degrades to Carto Dark,
 *  so the map never 403s on a missing key. */
const MAPTILER_KEY = (import.meta.env.VITE_MAPTILER_KEY as string | undefined) ?? '';
export const maptilerEnabled = MAPTILER_KEY.length > 0;

function cartoSource(name: CartoBasemap): RasterSourceSpecification {
  return {
    type: 'raster',
    tiles: ['a', 'b', 'c'].map(
      (s) => `https://${s}.basemaps.cartocdn.com/${CARTO_TILESET[name]}/{z}/{x}/{y}.png`,
    ),
    tileSize: 256,
    attribution: CARTO_ATTRIBUTION,
  };
}

/** MapTiler Satellite Hybrid via its TileJSON — MapLibre reads the tile URLs,
 *  tile size, and (license-required) attribution straight from it, so swapping
 *  to this source credits MapTiler correctly without a manual attribution set. */
function maptilerHybridSource(key: string): RasterSourceSpecification {
  return { type: 'raster', url: `https://api.maptiler.com/maps/hybrid/tiles.json?key=${key}` };
}

/** The raster source for a basemap choice. `satellite` needs a MapTiler key;
 *  without one it degrades to Carto Dark rather than failing. Exposed so a
 *  mounted map can rebuild just the `basemap` source on a pref change — keeping
 *  the app's tower/parcel/solar layers untouched, and picking up the new
 *  source's attribution (which `setTiles` alone can't update). */
export function basemapSource(name: BasemapName): RasterSourceSpecification {
  if (name === 'satellite') {
    return maptilerEnabled ? maptilerHybridSource(MAPTILER_KEY) : cartoSource('dark');
  }
  return cartoSource(name);
}

/** A MapLibre style for the chosen basemap. */
export function basemapStyle(name: BasemapName): StyleSpecification {
  return {
    version: 8,
    sources: { basemap: basemapSource(name) },
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
