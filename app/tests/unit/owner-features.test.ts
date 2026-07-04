import { describe, it, expect } from 'vitest';
import {
  coerceOwnerFeatures,
  computeOwnerExtents,
  type OwnerFeatures,
} from '../../src/lib/owner-features';

/** A fully-specified OwnerFeatures for the extents tests. */
function feat(over: Partial<OwnerFeatures> = {}): OwnerFeatures {
  return {
    states: [],
    counties: [],
    owner_kind: '',
    distress_tier: '',
    in_oz: false,
    in_qct: false,
    persistent_poverty: false,
    score: 0,
    parcel_count: 1,
    total_assessed_value: 0,
    tower_count: 0,
    solar_count: 0,
    structure_count: 1,
    structure_types: [],
    active_tower_count: 0,
    tallest_tower_height_m: null,
    carrier_count: 0,
    ...over,
  };
}

describe('coerceOwnerFeatures', () => {
  it('coerces a full raw owner into typed feature columns', () => {
    const o = coerceOwnerFeatures({
      owner_kind: 'llc',
      states: ['AR', 'WV'],
      counties: ['05119'],
      distress_tier: 'distressed',
      in_oz: true,
      in_qct: true,
      persistent_poverty: true,
      score: 0.8,
      parcel_count: 4,
      tower_count: 2,
      solar_count: 1,
      structure_count: 3,
      structure_types: ['tower', 'solar'],
      active_tower_count: 2,
      total_assessed_value: 25000,
      tallest_tower_height_m: 120,
      carrier_count: 3,
    });
    expect(o).toEqual({
      owner_kind: 'llc',
      states: ['AR', 'WV'],
      counties: ['05119'],
      distress_tier: 'distressed',
      in_oz: true,
      in_qct: true,
      persistent_poverty: true,
      score: 0.8,
      parcel_count: 4,
      tower_count: 2,
      solar_count: 1,
      structure_count: 3,
      structure_types: ['tower', 'solar'],
      active_tower_count: 2,
      total_assessed_value: 25000,
      tallest_tower_height_m: 120,
      carrier_count: 3,
    });
  });

  it('degrades missing fields to no-constraint defaults (tolerant of a stale index)', () => {
    const o = coerceOwnerFeatures({});
    expect(o.owner_kind).toBe('');
    expect(o.distress_tier).toBe('');
    expect(o.states).toEqual([]);
    expect(o.counties).toEqual([]);
    expect(o.structure_types).toEqual([]);
    expect(o.in_oz).toBe(false);
    expect(o.in_qct).toBe(false);
    expect(o.persistent_poverty).toBe(false);
    expect(o.score).toBe(0);
    expect(o.parcel_count).toBe(0);
    expect(o.tower_count).toBe(0);
    expect(o.carrier_count).toBe(0);
    // A missing height is null (no tower), not 0.
    expect(o.tallest_tower_height_m).toBeNull();
  });

  it('keeps an explicit null height null, and coerces a numeric height', () => {
    expect(coerceOwnerFeatures({ tallest_tower_height_m: null }).tallest_tower_height_m).toBeNull();
    expect(coerceOwnerFeatures({ tallest_tower_height_m: 42.5 }).tallest_tower_height_m).toBe(42.5);
  });

  it('falls back to 0 for non-finite numerics and treats only true as true', () => {
    const o = coerceOwnerFeatures({
      score: 'oops',
      parcel_count: Infinity,
      tallest_tower_height_m: 'nope',
      in_oz: 'yes', // any non-boolean-true is false
      structure_types: 'not-an-array',
    });
    expect(o.score).toBe(0);
    expect(o.parcel_count).toBe(0);
    expect(o.tallest_tower_height_m).toBe(0); // present-but-unparseable → 0, not null
    expect(o.in_oz).toBe(false);
    expect(o.structure_types).toEqual([]);
  });
});

describe('computeOwnerExtents', () => {
  it('returns the per-column floors for an empty index', () => {
    expect(computeOwnerExtents([])).toEqual({
      assessedMax: 0,
      portfolioMax: 1,
      heightMax: 0,
      structureCountMax: 1,
      towerMax: 1,
      carrierMax: 1,
    });
  });

  it('takes the max of each column in one pass', () => {
    const ext = computeOwnerExtents([
      feat({ total_assessed_value: 100, parcel_count: 3, tower_count: 5, structure_count: 6, carrier_count: 2, tallest_tower_height_m: 80 }),
      feat({ total_assessed_value: 900, parcel_count: 2, tower_count: 1, structure_count: 4, carrier_count: 7, tallest_tower_height_m: 120 }),
      feat({ total_assessed_value: 50, parcel_count: 9, tower_count: 3, structure_count: 2, carrier_count: 1, tallest_tower_height_m: null }),
    ]);
    expect(ext).toEqual({
      assessedMax: 900,
      portfolioMax: 9,
      heightMax: 120,
      structureCountMax: 6,
      towerMax: 5,
      carrierMax: 7,
    });
  });

  it('never drops a column below its floor and reads null height as 0', () => {
    const ext = computeOwnerExtents([
      feat({ parcel_count: 0, tower_count: 0, structure_count: 0, carrier_count: 0, tallest_tower_height_m: null, total_assessed_value: 0 }),
    ]);
    expect(ext).toEqual({
      assessedMax: 0,
      portfolioMax: 1,
      heightMax: 0,
      structureCountMax: 1,
      towerMax: 1,
      carrierMax: 1,
    });
  });
});
