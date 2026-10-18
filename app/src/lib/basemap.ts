/**
 * Basemap + initial-view helpers (PRD #121) — pure, so they unit-test cleanly
 * (the live MapLibre map is e2e territory).
 *
 * Three keyless Esri raster basemaps, plus an optional MapTiler Satellite
 * Hybrid (imagery + baked labels) gated on a client-side key:
 *   - `light`     → Esri Light Gray Canvas (`World_Light_Gray_Base`)
 *   - `voyager`   → Esri World Street Map  (`World_Street_Map`)
 *   - `dark`      → Esri Dark Gray Canvas  (`World_Dark_Gray_Base`)
 *   - `satellite` → MapTiler Satellite Hybrid (needs `VITE_MAPTILER_KEY`)
 */

import type { RasterSourceSpecification, StyleSpecification } from 'maplibre-gl';

export type BasemapName = 'light' | 'voyager' | 'dark' | 'satellite';

/** The keyless Esri raster basemaps. (Carto's CDN now requires an API key
 *  and watermarks every tile without one.) */
type KeylessBasemap = 'light' | 'voyager' | 'dark';

/** Esri map service per basemap choice. */
const ESRI_SERVICE: Record<KeylessBasemap, string> = {
  light: 'Canvas/World_Light_Gray_Base',
  voyager: 'World_Street_Map',
  dark: 'Canvas/World_Dark_Gray_Base',
};

const ESRI_ATTRIBUTION =
  'Powered by <a href="https://www.esri.com">Esri</a> &copy; Esri, HERE, Garmin, ' +
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/** MapTiler key (client-side, referrer-restricted). Absent → Satellite is
 *  hidden in settings and any stored `satellite` pref degrades to Esri Dark Gray,
 *  so the map never 403s on a missing key. */
const MAPTILER_KEY = (import.meta.env.VITE_MAPTILER_KEY as string | undefined) ?? '';
export const maptilerEnabled = MAPTILER_KEY.length > 0;

function esriSource(name: KeylessBasemap): RasterSourceSpecification {
  return {
    type: 'raster',
    tiles: [
      `https://server.arcgisonline.com/ArcGIS/rest/services/${ESRI_SERVICE[name]}/MapServer/tile/{z}/{y}/{x}`,
    ],
    tileSize: 256,
    attribution: ESRI_ATTRIBUTION,
  };
}

/** MapTiler Satellite Hybrid via its TileJSON — MapLibre reads the tile URLs,
 *  tile size, and (license-required) attribution straight from it, so swapping
 *  to this source credits MapTiler correctly without a manual attribution set. */
function maptilerHybridSource(key: string): RasterSourceSpecification {
  return { type: 'raster', url: `https://api.maptiler.com/maps/hybrid/tiles.json?key=${key}` };
}

/** The raster source for a basemap choice. `satellite` needs a MapTiler key;
 *  without one it degrades to Esri Dark Gray rather than failing. Exposed so a
 *  mounted map can rebuild just the `basemap` source on a pref change — keeping
 *  the app's tower/parcel/solar layers untouched, and picking up the new
 *  source's attribution (which `setTiles` alone can't update). */
export function basemapSource(name: BasemapName): RasterSourceSpecification {
  if (name === 'satellite') {
    return maptilerEnabled ? maptilerHybridSource(MAPTILER_KEY) : esriSource('dark');
  }
  return esriSource(name);
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
