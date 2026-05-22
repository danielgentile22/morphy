import { describe, it, expect } from 'vitest';
import { parseFacets, facetValues, facetRange } from '../../src/lib/facets';

const RAW = {
  schema_version: 1,
  state_fips: '05',
  total: 2116976,
  categorical: {
    owner_kind: [
      { value: 'llc', count: 358000 },
      { value: 'trust', count: 248000 },
      { value: '', count: 5 }, // blank value — dropped
    ],
    distress_tier: [{ value: 'distressed', count: 900000 }],
  },
  numeric: {
    assessed_value: { min: 0, max: 5_000_000 },
    acreage: { min: 0.1, max: 48_000 },
  },
};

describe('parseFacets', () => {
  it('parses categorical + numeric facets', () => {
    const f = parseFacets(RAW);
    expect(f.total).toBe(2116976);
    expect(f.categorical.owner_kind.map((v) => v.value)).toEqual(['llc', 'trust']);
    expect(f.numeric.assessed_value).toEqual({ min: 0, max: 5_000_000 });
  });

  it('drops blank categorical values', () => {
    const f = parseFacets(RAW);
    expect(f.categorical.owner_kind.some((v) => v.value === '')).toBe(false);
  });

  it('throws on a non-object root', () => {
    expect(() => parseFacets(null)).toThrow(/facets\.json/);
  });

  it('tolerates missing sections', () => {
    const f = parseFacets({ total: 10 });
    expect(f.total).toBe(10);
    expect(f.categorical).toEqual({});
    expect(f.numeric).toEqual({});
  });
});

describe('facet selectors', () => {
  const f = parseFacets(RAW);
  it('facetValues returns a column, or empty', () => {
    expect(facetValues(f, 'distress_tier')).toHaveLength(1);
    expect(facetValues(f, 'missing')).toEqual([]);
  });
  it('facetRange returns a column range, or null', () => {
    expect(facetRange(f, 'acreage')).toEqual({ min: 0.1, max: 48_000 });
    expect(facetRange(f, 'missing')).toBeNull();
  });
});
