import { describe, it, expect } from 'vitest';
import type { Catalog } from '../../src/lib/catalog';
import type { StateEntry } from '../../src/lib/catalog';
import {
  defaultVisibility,
  eagerAssets,
  errMsg,
  HEAVY_VIEWS,
  HIDDEN_LAYERS,
  pickInitialState,
  unionBounds,
} from '../../src/lib/stores-helpers';

const STATE_FIELDS: Omit<StateEntry, 'fips'> = {
  abbr: '',
  name: '',
  bbox: [0, 0, 0, 0],
  counts: {},
};

function fakeCatalog(overrides: Partial<Catalog> = {}): Catalog {
  return {
    schemaVersion: 1,
    generatedAt: '2026-05-27',
    state: { fips: '05', abbr: 'AR', name: 'Arkansas' },
    layers: [],
    views: [],
    ...overrides,
  } as Catalog;
}

describe('eagerAssets', () => {
  it('returns catalog layers with a geojsonPath, excluding heavy / map-owned / hidden — and never views', () => {
    const catalog = fakeCatalog({
      layers: [
        // map-owned: drawn as the global clustered tower layer, not per-state
        { name: 'towers', geojsonPath: 't.geojson', rows: 1 },
        { name: 'solar_facilities', geojsonPath: 's.geojson', rows: 1 },
        // hidden: distress is a filter field now, not a map overlay
        { name: 'distress_overlays', geojsonPath: 'd.geojson', rows: 1 },
        { name: 'no_path', geojsonPath: null, rows: 1 },
      ] as any,
      // Views (derived outreach segments) are retired — never eager-loaded.
      views: [
        { name: 'interestingness_top_1000', geojsonPath: 'i.geojson', rows: 1 },
        { name: 'parcels_hosting_infra', geojsonPath: 'ph.geojson', rows: 1 },
      ] as any,
    });
    const got = eagerAssets(catalog);
    expect(got.map((a) => a.name)).toEqual(['solar_facilities']);
  });
});

describe('defaultVisibility', () => {
  it('marks only DEFAULT_ON layers visible, omits hidden layers and all views', () => {
    const catalog = fakeCatalog({
      layers: [
        { name: 'towers', geojsonPath: 't.geojson', rows: 1 },
        { name: 'solar_facilities', geojsonPath: 's.geojson', rows: 1 },
        { name: 'distress_overlays', geojsonPath: 'd.geojson', rows: 1 },
      ] as any,
      views: [{ name: 'interestingness_top_1000', geojsonPath: 'i.geojson', rows: 1 }] as any,
    });
    expect(defaultVisibility(catalog)).toEqual({
      towers: true,
      solar_facilities: false,
    });
  });
  it('skips entries without geojsonPath', () => {
    const catalog = fakeCatalog({
      layers: [{ name: 'towers', geojsonPath: null, rows: 0 }] as any,
    });
    expect(defaultVisibility(catalog)).toEqual({});
  });
});

describe('HIDDEN_LAYERS sentinel set', () => {
  it('hides distress_overlays from the map + panel (it is a filter field now)', () => {
    expect(HIDDEN_LAYERS.has('distress_overlays')).toBe(true);
    expect(HIDDEN_LAYERS.has('towers')).toBe(false);
    expect(HIDDEN_LAYERS.has('solar_facilities')).toBe(false);
  });
});

describe('unionBounds', () => {
  it('unions state bboxes into [[w, s], [e, n]] fit corners', () => {
    // AR + MT — the union should span the westmost/southmost to eastmost/northmost.
    expect(
      unionBounds([
        { bbox: [-94.62, 33.0, -89.64, 36.5] },
        { bbox: [-116.06, 44.36, -104.04, 49.0] },
      ]),
    ).toEqual([
      [-116.06, 33.0],
      [-89.64, 49.0],
    ]);
  });
  it('returns the single bbox corners for one state', () => {
    expect(unionBounds([{ bbox: [-94.62, 33.0, -89.64, 36.5] }])).toEqual([
      [-94.62, 33.0],
      [-89.64, 36.5],
    ]);
  });
  it('is null when there are no states', () => {
    expect(unionBounds([])).toBeNull();
  });
});

describe('pickInitialState', () => {
  const states: StateEntry[] = [
    { ...STATE_FIELDS, fips: '05' },
    { ...STATE_FIELDS, fips: '30' },
  ];

  it('honours a valid ?state= request', () => {
    expect(pickInitialState('?state=30', states)).toEqual({
      fips: '30',
      invalidRequest: null,
    });
  });

  it('falls back to the first state when ?state= is missing', () => {
    expect(pickInitialState('', states)).toEqual({
      fips: '05',
      invalidRequest: null,
    });
  });

  it('reports an unknown ?state= via invalidRequest', () => {
    expect(pickInitialState('?state=99', states)).toEqual({
      fips: '05',
      invalidRequest: '99',
    });
  });

  it('treats whitespace-only ?state= as missing', () => {
    expect(pickInitialState('?state=%20%20', states)).toEqual({
      fips: '05',
      invalidRequest: null,
    });
  });

  it('returns an empty fips when no states exist', () => {
    expect(pickInitialState('', [])).toEqual({ fips: '', invalidRequest: null });
  });
});

describe('errMsg', () => {
  it('uses the Error message for Error instances', () => {
    expect(errMsg(new Error('boom'))).toBe('boom');
  });
  it('coerces non-Error throws', () => {
    expect(errMsg('lit')).toBe('lit');
    expect(errMsg(404)).toBe('404');
  });
});

describe('HEAVY_VIEWS sentinel set', () => {
  it('includes the four large-GeoJSON views', () => {
    expect(HEAVY_VIEWS.has('parcels_hosting_infra')).toBe(true);
    expect(HEAVY_VIEWS.has('distressed_parcels_hosting_infra')).toBe(true);
    expect(HEAVY_VIEWS.has('llc_owned_parcels_with_infra')).toBe(true);
    expect(HEAVY_VIEWS.has('towers_with_landowner')).toBe(true);
  });
  it('does not include the small / eager assets', () => {
    expect(HEAVY_VIEWS.has('towers')).toBe(false);
    expect(HEAVY_VIEWS.has('interestingness_top_1000')).toBe(false);
  });
});
