import { describe, it, expect } from 'vitest';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import { mergeSolarPoints, showSolarLayer, solarTotal, type SolarProps } from '../../src/lib/solar';
import { emptyFilterModel } from '../../src/lib/filter-model';
import { parseCompositeIndex } from '../../src/lib/catalog';

function solar(
  coords: [number, number] | null,
  props: Partial<SolarProps & { capacity_mw: number | null }> = {},
  geomType: Geometry['type'] = 'Point',
): Feature {
  const geometry =
    coords === null
      ? ({ type: 'Point', coordinates: [Number.NaN, Number.NaN] } as Geometry)
      : geomType === 'Point'
        ? ({ type: 'Point', coordinates: coords } as Geometry)
        : ({ type: 'Polygon', coordinates: [[coords, coords, coords, coords]] } as Geometry);
  return {
    type: 'Feature',
    geometry,
    properties: {
      name: 'Carpenter',
      operator: 'Entergy Arkansas LLC',
      capacity_mw: 12.5,
      ...props,
    },
  };
}

function fc(features: Feature[]): FeatureCollection {
  return { type: 'FeatureCollection', features };
}

describe('mergeSolarPoints', () => {
  it('unions every state into one national collection (mirrors loadTowerPoints)', () => {
    const out = mergeSolarPoints([
      { state: '05', collection: fc([solar([-91, 34]), solar([-92, 35])]) },
      { state: '30', collection: fc([solar([-110, 46])]) },
    ]);
    expect(out.type).toBe('FeatureCollection');
    expect(out.features).toHaveLength(3);
    expect(out.features.map((f) => f.properties.state)).toEqual(['05', '05', '30']);
  });

  it('maps a feature to a slim [lon, lat] Point with flat props', () => {
    const out = mergeSolarPoints([
      {
        state: '05',
        collection: fc([solar([-91.3, 33.0], { name: 'Carpenter', operator: 'Entergy', capacity_mw: 100 })]),
      },
    ]);
    expect(out.features[0].geometry).toEqual({ type: 'Point', coordinates: [-91.3, 33.0] });
    expect(out.features[0].properties).toEqual({
      name: 'Carpenter',
      operator: 'Entergy',
      state: '05',
      capacity_mw: 100,
    });
  });

  it('drops features without finite coordinates', () => {
    const out = mergeSolarPoints([
      { state: '05', collection: fc([solar(null), solar([-91, 34], { name: 'keep' })]) },
    ]);
    expect(out.features).toHaveLength(1);
    expect(out.features[0].properties.name).toBe('keep');
  });

  it('drops non-Point geometries (solar facilities render as points only)', () => {
    const out = mergeSolarPoints([
      { state: '05', collection: fc([solar([-91, 34], {}, 'Polygon'), solar([-92, 35], { name: 'pt' })]) },
    ]);
    expect(out.features).toHaveLength(1);
    expect(out.features[0].properties.name).toBe('pt');
  });

  it('normalizes missing name/operator to blank and missing capacity to null', () => {
    const out = mergeSolarPoints([
      {
        state: '12',
        collection: fc([
          { type: 'Feature', geometry: { type: 'Point', coordinates: [-81, 28] }, properties: {} },
        ]),
      },
    ]);
    expect(out.features[0].properties).toEqual({
      name: '',
      operator: '',
      state: '12',
      capacity_mw: null,
    });
  });

  it('is an empty collection for no inputs', () => {
    expect(mergeSolarPoints([])).toEqual({ type: 'FeatureCollection', features: [] });
  });
});

describe('showSolarLayer', () => {
  it('is hidden for the default model (solar off by default)', () => {
    expect(showSolarLayer(emptyFilterModel())).toBe(false);
  });

  it('is shown iff the Structure-type filter includes solar', () => {
    expect(showSolarLayer({ ...emptyFilterModel(), structureTypes: ['solar'] })).toBe(true);
    expect(showSolarLayer({ ...emptyFilterModel(), structureTypes: ['tower', 'solar'] })).toBe(true);
    expect(showSolarLayer({ ...emptyFilterModel(), structureTypes: ['tower'] })).toBe(false);
  });
});

describe('solarTotal', () => {
  function index(counts: number[]) {
    return parseCompositeIndex({
      schema_version: 1,
      generated_at: '',
      states: counts.map((c, i) => ({
        fips: String(i).padStart(2, '0'),
        abbr: 'XX',
        name: 'X',
        bbox: [0, 0, 0, 0],
        counts: { solar_facility: c },
      })),
    });
  }

  it('sums each state solar_facility count for the static Solar tile', () => {
    // AR 208 + FL 607 + MT 92 + WV 60 = 967 (the live anchor totals).
    expect(solarTotal(index([208, 607, 92, 60]))).toBe(967);
  });

  it('treats a missing solar_facility count as zero', () => {
    const idx = parseCompositeIndex({
      schema_version: 1,
      generated_at: '',
      states: [
        { fips: '05', abbr: 'AR', name: 'AR', bbox: [0, 0, 0, 0], counts: { solar_facility: 5 } },
        { fips: '30', abbr: 'MT', name: 'MT', bbox: [0, 0, 0, 0], counts: {} },
      ],
    });
    expect(solarTotal(idx)).toBe(5);
  });

  it('is zero for a null index or no states', () => {
    expect(solarTotal(null)).toBe(0);
    expect(solarTotal(index([]))).toBe(0);
  });
});
