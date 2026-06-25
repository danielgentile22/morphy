import { describe, it, expect } from 'vitest';
import {
  basemapStyle,
  basemapSource,
  maptilerEnabled,
  resolveInitialView,
  parseMapView,
  type MapView,
} from '../../src/lib/basemap';

/** The single raster tileset a style points at (the bit that varies). */
function tilesetOf(style: ReturnType<typeof basemapStyle>): string {
  const src = style.sources.basemap as { tiles: string[] };
  return src.tiles[0];
}

describe('basemapStyle — keyless Carto raster per basemap choice (PRD #121)', () => {
  it('maps each basemap choice to its Carto tileset (honoured literally)', () => {
    // The chrome is dark-only Halo, so the pick is honoured as-is — no theme nudge.
    expect(tilesetOf(basemapStyle('light'))).toContain('light_all'); // Positron
    expect(tilesetOf(basemapStyle('voyager'))).toContain('voyager');
    expect(tilesetOf(basemapStyle('dark'))).toContain('dark_all'); // Dark Matter
  });

  it('produces a valid single-layer raster style', () => {
    const s = basemapStyle('light');
    expect(s.version).toBe(8);
    expect(s.layers).toHaveLength(1);
    expect(s.layers[0]).toMatchObject({ type: 'raster', source: 'basemap' });
    // keyless: the CDN host carries no API key
    expect(tilesetOf(s)).toContain('basemaps.cartocdn.com');
  });
});

describe('basemapSource — satellite resolves by MapTiler key presence', () => {
  // `maptilerEnabled` reflects VITE_MAPTILER_KEY at build time, so this asserts
  // the contract in *either* environment: keyed (a dev .env.local) → MapTiler;
  // keyless (CI) → the Carto Dark fallback that can never 403.
  it('routes `satellite` to MapTiler when keyed, Carto Dark when not', () => {
    const src = basemapSource('satellite') as { tiles?: string[]; url?: string };
    if (maptilerEnabled) {
      expect(src.url).toContain('api.maptiler.com/maps/hybrid');
    } else {
      expect(src.url).toBeUndefined(); // not the MapTiler TileJSON
      expect(src.tiles?.[0]).toContain('dark_all'); // safe keyless fallback
    }
  });
});

describe('resolveInitialView — where the map opens (PRD #121)', () => {
  const home: MapView = { lng: -92.1, lat: 34.7, zoom: 11.5 };
  const last: MapView = { lng: -111.0, lat: 46.0, zoom: 6 };

  it('opens on the pinned home when view_mode is home and a home exists', () => {
    expect(resolveInitialView({ viewMode: 'home', home }, last)).toEqual(home);
  });

  it('falls back to where I left off when home is requested but unset', () => {
    expect(resolveInitialView({ viewMode: 'home', home: null }, last)).toEqual(last);
  });

  it('restores the last position in last mode', () => {
    expect(resolveInitialView({ viewMode: 'last', home }, last)).toEqual(last);
  });

  it('returns null (→ the app default view) when nothing is saved', () => {
    expect(resolveInitialView({ viewMode: 'last', home: null }, null)).toBeNull();
    expect(resolveInitialView({ viewMode: 'home', home: null }, null)).toBeNull();
  });
});

describe('parseMapView — stored camera blob', () => {
  it('parses a well-formed view', () => {
    expect(parseMapView('{"lng":-92.1,"lat":34.7,"zoom":11.5}')).toEqual({
      lng: -92.1,
      lat: 34.7,
      zoom: 11.5,
    });
  });

  it('treats empty / malformed / incomplete blobs as unset', () => {
    expect(parseMapView('')).toBeNull();
    expect(parseMapView('not json')).toBeNull();
    expect(parseMapView('{"lng":-92.1}')).toBeNull(); // missing lat/zoom
    expect(parseMapView('{"lng":"x","lat":1,"zoom":2}')).toBeNull(); // wrong type
    expect(parseMapView('{"lng":null,"lat":1,"zoom":2}')).toBeNull();
  });
});
