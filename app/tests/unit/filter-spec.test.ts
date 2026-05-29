import { describe, expect, it } from 'vitest';
import { FILTER_SPECS, emptyFilters, type FilterState } from '../../src/lib/filters';

describe('FILTER_SPECS coverage', () => {
  it('covers every FilterState field exactly once', () => {
    const fieldNames = Object.keys(emptyFilters()) as (keyof FilterState)[];
    const specIds = FILTER_SPECS.map((s) => s.id);
    expect(new Set(specIds).size).toBe(specIds.length); // no dupes
    expect(specIds.sort()).toEqual(fieldNames.sort());
  });

  it('emits unique SQL columns', () => {
    const columns = FILTER_SPECS.map((s) => s.column);
    expect(new Set(columns).size).toBe(columns.length);
  });

  it('no spec is active on a fresh empty filter state', () => {
    const empty = emptyFilters();
    for (const spec of FILTER_SPECS) {
      expect(spec.isActive(empty)).toBe(false);
      expect(spec.toSQL(empty)).toBeNull();
    }
  });

  it('isActive ↔ toSQL agree across every spec', () => {
    // For each spec, build a representative active state by mutating
    // only its field. isActive must be true and toSQL must return a
    // non-null fragment containing the spec's column name.
    const samples: Record<keyof FilterState, Partial<FilterState>> = {
      ownerKind: { ownerKind: ['llc'] },
      distressTier: { distressTier: ['distressed'] },
      countyFips: { countyFips: ['05001'] },
      hasTower: { hasTower: true },
      hasSolar: { hasSolar: true },
      inOz: { inOz: true },
      inQct: { inQct: true },
      persistentPoverty: { persistentPoverty: true },
      scoreMin: { scoreMin: 0.5 },
      clusterSizeMin: { clusterSizeMin: 5 },
      assessedValue: { assessedValue: [1000, 50000] },
      acreage: { acreage: [10, 500] },
      ownerClusterId: { ownerClusterId: 'cluster-abc' },
    };
    for (const spec of FILTER_SPECS) {
      const state = { ...emptyFilters(), ...samples[spec.id] };
      expect(spec.isActive(state)).toBe(true);
      const sql = spec.toSQL(state);
      expect(sql).not.toBeNull();
      expect(sql).toContain(spec.column);
    }
  });
});
