import { describe, it, expect } from 'vitest';
import type { Catalog } from '../../src/lib/catalog';
import type { StateEntry } from '../../src/lib/catalog';
import {
  defaultVisibility,
  eagerAssets,
  errMsg,
  HEAVY_VIEWS,
  pickInitialState,
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
  it('returns layers + views with a geojsonPath, excluding HEAVY_VIEWS', () => {
    const catalog = fakeCatalog({
      layers: [
        { name: 'towers', geojsonPath: 't.geojson', rows: 1 },
        { name: 'no_path', geojsonPath: null, rows: 1 },
      ] as any,
      views: [
        { name: 'interestingness_top_1000', geojsonPath: 'i.geojson', rows: 1 },
        // heavy view — excluded
        { name: 'parcels_hosting_infra', geojsonPath: 'ph.geojson', rows: 1 },
      ] as any,
    });
    const got = eagerAssets(catalog);
    expect(got.map((a) => a.name)).toEqual(['towers', 'interestingness_top_1000']);
  });
});

describe('defaultVisibility', () => {
  it('only marks DEFAULT_ON layers + views as visible', () => {
    const catalog = fakeCatalog({
      layers: [
        { name: 'towers', geojsonPath: 't.geojson', rows: 1 },
        { name: 'solar_facilities', geojsonPath: 's.geojson', rows: 1 },
      ] as any,
      views: [
        { name: 'interestingness_top_1000', geojsonPath: 'i.geojson', rows: 1 },
        { name: 'parcels_hosting_infra', geojsonPath: 'ph.geojson', rows: 1 },
      ] as any,
    });
    expect(defaultVisibility(catalog)).toEqual({
      towers: true,
      solar_facilities: false,
      interestingness_top_1000: true,
      parcels_hosting_infra: false,
    });
  });
  it('skips entries without geojsonPath', () => {
    const catalog = fakeCatalog({
      layers: [{ name: 'towers', geojsonPath: null, rows: 0 }] as any,
    });
    expect(defaultVisibility(catalog)).toEqual({});
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
