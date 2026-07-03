import { describe, it, expect } from 'vitest';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import {
  mergeCountyBoundaries,
  countyLayerAppearance,
  COUNTIES_LAYER,
} from '../../src/lib/county-layers';
import { Z_ON } from '../../src/lib/parcel-layers';

const SQUARE: Geometry = {
  type: 'Polygon',
  coordinates: [
    [
      [-91, 34],
      [-90, 34],
      [-90, 35],
      [-91, 35],
      [-91, 34],
    ],
  ],
};

function county(props: Record<string, unknown>, geometry: Geometry = SQUARE): Feature {
  return { type: 'Feature', geometry, properties: props };
}

function fc(features: Feature[]): FeatureCollection {
  return { type: 'FeatureCollection', features };
}

describe('mergeCountyBoundaries', () => {
  it('unions every state into one national collection and stamps the state', () => {
    const out = mergeCountyBoundaries([
      { state: '05', collection: fc([county({ county_fips: '05001' }), county({ county_fips: '05003' })]) },
      { state: '54', collection: fc([county({ county_fips: '54001' })]) },
    ]);
    expect(out.type).toBe('FeatureCollection');
    expect(out.features).toHaveLength(3);
    expect(out.features.map((f) => f.properties.state)).toEqual(['05', '05', '54']);
  });

  it('keeps Polygon and MultiPolygon geometries, drops everything else', () => {
    const multi: Geometry = {
      type: 'MultiPolygon',
      coordinates: [
        [
          [
            [-91, 34],
            [-90, 34],
            [-90, 35],
            [-91, 34],
          ],
        ],
      ],
    };
    const point: Geometry = { type: 'Point', coordinates: [-91, 34] };
    const out = mergeCountyBoundaries([
      {
        state: '05',
        collection: fc([
          county({ county_name: 'poly' }),
          county({ county_name: 'multi' }, multi),
          county({ county_name: 'point' }, point),
        ]),
      },
    ]);
    expect(out.features.map((f) => f.properties.county_name)).toEqual(['poly', 'multi']);
  });

  it('normalizes distress fields: missing tier → "", persistent_poverty → boolean', () => {
    const out = mergeCountyBoundaries([
      {
        state: '30',
        collection: fc([
          county({ county_fips: '30001', county_name: 'Beaverhead', tier: null, persistent_poverty: null }),
          county({ county_fips: '54047', county_name: 'McDowell', tier: 'distressed', persistent_poverty: true }),
        ]),
      },
    ]);
    expect(out.features[0].properties).toEqual({
      county_fips: '30001',
      county_name: 'Beaverhead',
      state: '30',
      tier: '',
      persistent_poverty: false,
    });
    expect(out.features[1].properties.tier).toBe('distressed');
    expect(out.features[1].properties.persistent_poverty).toBe(true);
  });

  it('is an empty collection for no inputs', () => {
    expect(mergeCountyBoundaries([])).toEqual({ type: 'FeatureCollection', features: [] });
  });
});

describe('countyLayerAppearance', () => {
  it('hands off exactly where the parcel pop-in ramp completes (Z_ON + 0.5)', () => {
    expect(countyLayerAppearance().maxzoom).toBe(Z_ON + 0.5);
    expect(countyLayerAppearance(10).maxzoom).toBe(10.5);
  });

  it('shades subtly — context opacity below the parcel fill', () => {
    const a = countyLayerAppearance();
    expect(a.fillOpacity).toBeGreaterThan(0);
    expect(a.fillOpacity).toBeLessThan(0.55); // parcels' FILL_OPACITY
    expect(a.lineOpacity).toBeGreaterThan(0);
    expect(a.lineOpacity).toBeLessThanOrEqual(1);
  });
});

describe('COUNTIES_LAYER key', () => {
  it('is stable (absent from boot defaults → off by default)', () => {
    expect(COUNTIES_LAYER).toBe('counties');
  });
});
