import { describe, it, expect } from 'vitest';
import { emptyFilters, isAnyFilterActive, activeFilterCount } from '../../src/lib/filters';

describe('emptyFilters', () => {
  it('is fully unconstrained', () => {
    const f = emptyFilters();
    expect(f.ownerKind).toEqual([]);
    expect(f.scoreMin).toBe(0);
    expect(f.clusterSizeMin).toBe(1);
    expect(f.assessedValue).toBeNull();
    expect(f.ownerClusterId).toBeNull();
  });

  it('returns a fresh object each call', () => {
    expect(emptyFilters()).not.toBe(emptyFilters());
  });
});

describe('isAnyFilterActive', () => {
  it('is false for an empty filter state', () => {
    expect(isAnyFilterActive(emptyFilters())).toBe(false);
  });
  it('is true once any control is set', () => {
    expect(isAnyFilterActive({ ...emptyFilters(), hasTower: true })).toBe(true);
    expect(isAnyFilterActive({ ...emptyFilters(), ownerKind: ['llc'] })).toBe(true);
    expect(isAnyFilterActive({ ...emptyFilters(), scoreMin: 0.3 })).toBe(true);
    expect(isAnyFilterActive({ ...emptyFilters(), ownerClusterId: 'abc' })).toBe(true);
  });
});

describe('activeFilterCount', () => {
  it('counts each constraining control once', () => {
    expect(activeFilterCount(emptyFilters())).toBe(0);
    expect(
      activeFilterCount({
        ...emptyFilters(),
        ownerKind: ['llc', 'trust'],
        hasTower: true,
        scoreMin: 0.5,
      }),
    ).toBe(3);
  });
  it('treats the numeric sentinels as inactive', () => {
    expect(activeFilterCount({ ...emptyFilters(), scoreMin: 0, clusterSizeMin: 1 })).toBe(0);
  });
});
