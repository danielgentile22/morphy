import { describe, it, expect } from 'vitest';
import { parseCatalog, parseCompositeIndex, type Catalog } from '../../src/lib/catalog';
import {
  AppStore,
  eagerAssets,
  defaultVisibility,
  pickInitialState,
} from '../../src/lib/stores.svelte';

const RAW_CATALOG = {
  schema_version: 3,
  state_fips: '05',
  state_name: 'Arkansas',
  state_abbr: 'AR',
  generated_at: '2026-05-21T05:08:00+00:00',
  sources_used_versions: {},
  layers: {
    county_scores: { canonical_type: 'county_score', parquet_path: 'c.parquet', rows: 75, schema: {} },
    towers: {
      canonical_type: 'tower',
      geojson_path: 'towers.geojson',
      parquet_path: 't.parquet',
      rows: 15846,
      schema: {},
    },
    distress_overlays: {
      canonical_type: 'distress_overlay',
      geojson_path: 'distress_overlays.geojson',
      parquet_path: 'd.parquet',
      rows: 246,
      schema: {},
    },
  },
  views: {
    interestingness_top_1000: {
      description: '',
      geometry_type: 'MultiPolygon',
      inputs: ['parcel'],
      parquet_path: 'v.parquet',
      geojson_path: 'views/interestingness_top_1000.geojson',
      rows: 1000,
    },
    parcels_hosting_infra: {
      description: '',
      geometry_type: 'MultiPolygon',
      inputs: ['parcel'],
      parquet_path: 'v.parquet',
      geojson_path: 'views/parcels_hosting_infra.geojson',
      rows: 7287,
    },
    owner_clusters: {
      description: '',
      geometry_type: null,
      inputs: ['parcel'],
      parquet_path: 'v.parquet',
      rows: 111013,
    },
  },
};

const CATALOG: Catalog = parseCatalog(RAW_CATALOG);

const INDEX = parseCompositeIndex({
  schema_version: 1,
  generated_at: '',
  states: [
    { fips: '05', abbr: 'AR', name: 'Arkansas', bbox: [-94.6, 33, -89.6, 36.5], counts: {} },
    { fips: '30', abbr: 'MT', name: 'Montana', bbox: [-116, 44.3, -104, 49], counts: {} },
  ],
});

describe('eagerAssets', () => {
  it('eager-loads only renderable catalog layers — no views, hidden, or map-owned', () => {
    const names = eagerAssets(CATALOG).map((a) => a.name);
    // distress_overlays is a filter field now — hidden from the map.
    expect(names).not.toContain('distress_overlays');
    // Views (derived outreach segments) are retired — never eager-loaded.
    expect(names).not.toContain('interestingness_top_1000');
    expect(names).not.toContain('parcels_hosting_infra');
    // towers is map-owned (the global clustered layer) — not eager-loaded per state.
    expect(names).not.toContain('towers');
    // owner_clusters has no GeoJSON — not loadable at all.
    expect(names).not.toContain('owner_clusters');
  });
});

describe('defaultVisibility', () => {
  it('switches on towers by default and omits hidden distress overlays + views', () => {
    const vis = defaultVisibility(CATALOG);
    expect(vis.towers).toBe(true);
    expect(vis).not.toHaveProperty('distress_overlays');
    expect(vis).not.toHaveProperty('interestingness_top_1000');
    expect(vis).not.toHaveProperty('parcels_hosting_infra');
  });
  it('omits layers / views with no GeoJSON', () => {
    expect(defaultVisibility(CATALOG)).not.toHaveProperty('county_scores');
    expect(defaultVisibility(CATALOG)).not.toHaveProperty('owner_clusters');
  });
});

describe('pickInitialState', () => {
  it('uses a valid ?state= request', () => {
    expect(pickInitialState('?state=30', INDEX.states)).toEqual({
      fips: '30',
      invalidRequest: null,
    });
  });
  it('falls back to the first state when ?state= is absent', () => {
    expect(pickInitialState('', INDEX.states)).toEqual({ fips: '05', invalidRequest: null });
  });
  it('falls back and reports an unknown ?state=', () => {
    expect(pickInitialState('?state=99', INDEX.states)).toEqual({
      fips: '05',
      invalidRequest: '99',
    });
  });
});

describe('AppStore mutations', () => {
  it('sets and clears the selection', () => {
    const s = new AppStore();
    expect(s.selection).toBeNull();
    s.setSelection({ kind: 'parcel', props: { owner_name: 'X' } });
    expect(s.selection?.kind).toBe('parcel');
    s.clearSelection();
    expect(s.selection).toBeNull();
  });

  it('toggles and reads layer visibility', () => {
    const s = new AppStore();
    expect(s.isLayerVisible('towers')).toBe(false);
    s.setLayerVisible('towers', true);
    expect(s.isLayerVisible('towers')).toBe(true);
    s.toggleLayer('towers');
    expect(s.isLayerVisible('towers')).toBe(false);
  });

  it('dismisses a notice', () => {
    const s = new AppStore();
    s.notice = 'heads up';
    s.dismissNotice();
    expect(s.notice).toBeNull();
  });

  it('derives activeState from the index + active FIPS', () => {
    const s = new AppStore();
    expect(s.activeState).toBeNull();
    s.index = INDEX;
    s.activeFips = '30';
    expect(s.activeState?.name).toBe('Montana');
    s.activeFips = '05';
    expect(s.activeState?.name).toBe('Arkansas');
  });
});
