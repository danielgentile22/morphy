import { describe, it, expect } from 'vitest';
import {
  basemapStyle,
  resolveBasemapName,
  resolveInitialView,
  parseMapView,
  type MapView,
} from '../../src/lib/basemap';

/** The single raster tileset a style points at (the bit that varies). */
function tilesetOf(style: ReturnType<typeof basemapStyle>): string {
  const src = style.sources.basemap as { tiles: string[] };
  return src.tiles[0];
}

describe('basemapStyle — keyless Carto raster per (name, theme) (PRD #121)', () => {
  it('maps each basemap choice to its Carto tileset on the light theme', () => {
    expect(tilesetOf(basemapStyle('light', 'light'))).toContain('light_all'); // Positron
    expect(tilesetOf(basemapStyle('voyager', 'light'))).toContain('voyager');
    expect(tilesetOf(basemapStyle('dark', 'light'))).toContain('dark_all'); // Dark Matter
  });

  it('produces a valid single-layer raster style', () => {
    const s = basemapStyle('light', 'light');
    expect(s.version).toBe(8);
    expect(s.layers).toHaveLength(1);
    expect(s.layers[0]).toMatchObject({ type: 'raster', source: 'basemap' });
    // keyless: the CDN host carries no API key
    expect(tilesetOf(s)).toContain('basemaps.cartocdn.com');
  });

  it('nudges the default light basemap to a dark tileset under the dark theme', () => {
    // a bright map glaring inside a dark UI is the thing we avoid (overridable)
    expect(resolveBasemapName('light', 'dark')).toBe('dark');
    expect(tilesetOf(basemapStyle('light', 'dark'))).toContain('dark_all');
  });

  it('honours an explicit non-default basemap even under the dark theme', () => {
    expect(resolveBasemapName('voyager', 'dark')).toBe('voyager');
    expect(resolveBasemapName('dark', 'dark')).toBe('dark');
    expect(resolveBasemapName('light', 'light')).toBe('light');
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
