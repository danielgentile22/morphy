import { describe, it, expect } from 'vitest';
import {
  parseCompositeIndex,
  parseCatalog,
  geojsonLayers,
  geojsonViews,
  findLayer,
  findView,
  entityKind,
} from '../../src/lib/catalog';

// Minimal raw shapes mirroring the real index.json / catalog.json.
const RAW_INDEX = {
  schema_version: 1,
  generated_at: '2026-05-21T17:17:59+00:00',
  states: [
    {
      fips: '05',
      abbr: 'AR',
      name: 'Arkansas',
      bbox: [-94.62, 33.0, -89.64, 36.5],
      counts: { parcel: 2116976, tower: 15846, bogus: 'x' },
    },
    {
      fips: '30',
      abbr: 'MT',
      name: 'Montana',
      bbox: [-116.06, 44.36, -104.04, 49.0],
      counts: { parcel: 920111 },
    },
  ],
};

const RAW_CATALOG = {
  schema_version: 3,
  state_fips: '05',
  state_name: 'Arkansas',
  state_abbr: 'AR',
  generated_at: '2026-05-21T05:08:00+00:00',
  layers: {
    towers: {
      canonical_type: 'tower',
      geojson_path: 'towers.geojson',
      geometry_type: 'Point',
      parquet_path: 'towers.parquet',
      rows: 15846,
      schema: { asr_number: 'str', height_m: 'float64' },
    },
    parcels: {
      canonical_type: 'parcel',
      geometry_type: 'MultiPolygon',
      parquet_path: 'parcels.parquet',
      rows: 2116976,
      schema: { parcel_id: 'str' },
    },
  },
  views: {
    interestingness_top_1000: {
      description: 'Top 1,000 parcels',
      geometry_type: 'MultiPolygon',
      inputs: ['parcel'],
      parquet_path: 'views/interestingness_top_1000.parquet',
      geojson_path: 'views/interestingness_top_1000.geojson',
      rows: 1000,
    },
    owner_clusters: {
      description: 'Owners holding >=2 parcels',
      geometry_type: null,
      inputs: ['parcel'],
      parquet_path: 'views/owner_clusters.parquet',
      rows: 111013,
    },
  },
  sources_used_versions: { fcc_asr: 'manual' },
};

describe('parseCompositeIndex', () => {
  it('parses a valid index', () => {
    const idx = parseCompositeIndex(RAW_INDEX);
    expect(idx.schemaVersion).toBe(1);
    expect(idx.states).toHaveLength(2);
    expect(idx.states[0]).toMatchObject({ fips: '05', abbr: 'AR', name: 'Arkansas' });
    expect(idx.states[0].bbox).toEqual([-94.62, 33.0, -89.64, 36.5]);
  });

  it('keeps only numeric counts', () => {
    const idx = parseCompositeIndex(RAW_INDEX);
    expect(idx.states[0].counts).toEqual({ parcel: 2116976, tower: 15846 });
  });

  it('throws on a non-object root', () => {
    expect(() => parseCompositeIndex(null)).toThrow(/index\.json/);
    expect(() => parseCompositeIndex('nope')).toThrow(/index\.json/);
  });

  it('throws when the states array is missing', () => {
    expect(() => parseCompositeIndex({ schema_version: 1 })).toThrow(/states/);
  });

  it('throws when a state has an invalid bbox', () => {
    const bad = { states: [{ fips: '05', abbr: 'AR', name: 'Arkansas', bbox: [1, 2, 3] }] };
    expect(() => parseCompositeIndex(bad)).toThrow(/bbox/);
  });

  it('throws when a state is missing its fips', () => {
    const bad = { states: [{ abbr: 'AR', bbox: [-94, 33, -89, 36] }] };
    expect(() => parseCompositeIndex(bad)).toThrow(/fips/);
  });
});

describe('parseCatalog', () => {
  it('parses layers into an array preserving order', () => {
    const cat = parseCatalog(RAW_CATALOG);
    expect(cat.stateFips).toBe('05');
    expect(cat.layers.map((l) => l.name)).toEqual(['towers', 'parcels']);
    expect(cat.layers[0].geojsonPath).toBe('towers.geojson');
    expect(cat.layers[1].geojsonPath).toBeUndefined();
  });

  it('parses views into an array', () => {
    const cat = parseCatalog(RAW_CATALOG);
    expect(cat.views.map((v) => v.name)).toEqual(['interestingness_top_1000', 'owner_clusters']);
    expect(cat.views[0].geojsonPath).toBe('views/interestingness_top_1000.geojson');
    expect(cat.views[1].geometryType).toBeNull();
  });

  it('throws when state_fips is missing', () => {
    expect(() => parseCatalog({ layers: {}, views: {} })).toThrow(/state_fips/);
  });

  it('throws on a non-object root', () => {
    expect(() => parseCatalog(null)).toThrow(/catalog\.json/);
  });
});

describe('catalog selectors', () => {
  const cat = parseCatalog(RAW_CATALOG);

  it('geojsonLayers returns only layers with a GeoJSON file', () => {
    expect(geojsonLayers(cat).map((l) => l.name)).toEqual(['towers']);
  });

  it('geojsonViews returns only views with a GeoJSON file', () => {
    expect(geojsonViews(cat).map((v) => v.name)).toEqual(['interestingness_top_1000']);
  });

  it('findLayer / findView locate by name', () => {
    expect(findLayer(cat, 'parcels')?.rows).toBe(2116976);
    expect(findLayer(cat, 'missing')).toBeUndefined();
    expect(findView(cat, 'owner_clusters')?.rows).toBe(111013);
  });
});

describe('entityKind', () => {
  const cat = parseCatalog(RAW_CATALOG);

  it('maps a layer from its canonical type', () => {
    expect(entityKind(cat, 'towers')).toBe('tower');
    expect(entityKind(cat, 'parcels')).toBe('parcel');
  });

  it('maps a view from its first input', () => {
    // interestingness_top_1000 has inputs ['parcel'].
    expect(entityKind(cat, 'interestingness_top_1000')).toBe('parcel');
  });

  it('returns null for an unknown name', () => {
    expect(entityKind(cat, 'nope')).toBeNull();
  });
});
