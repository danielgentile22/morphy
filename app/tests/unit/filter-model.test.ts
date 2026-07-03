import { describe, it, expect } from 'vitest';
import {
  composeOwnerWhere,
  matchesOwner,
  isAnyFilterActive,
  activeFilterCount,
  emptyFilterModel,
  serializeFilterModel,
  deserializeFilterModel,
  shouldApplyFilterDefault,
  summarizeFilterModel,
  FILTER_FIELDS,
  type FilterModel,
  type FilterableOwner,
} from '../../src/lib/filter-model';

function model(overrides: Partial<FilterModel>): FilterModel {
  return { ...emptyFilterModel(), ...overrides };
}

/** A fully-populated owner so a single active filter is what discriminates. */
function owner(overrides: Partial<FilterableOwner> = {}): FilterableOwner {
  return {
    states: ['AR'],
    counties: ['05119'],
    owner_kind: 'llc',
    distress_tier: 'distressed',
    in_oz: true,
    in_qct: true,
    persistent_poverty: true,
    score: 0.8,
    parcel_count: 4,
    total_assessed_value: 25000,
    tower_count: 2,
    solar_count: 1,
    structure_count: 3,
    structure_types: ['tower', 'solar'],
    active_tower_count: 2,
    tallest_tower_height_m: 120,
    carrier_count: 3,
    ...overrides,
  };
}

describe('composeOwnerWhere — byte-for-byte query contract', () => {
  it('is empty for an unconstrained model (empty filter = all)', () => {
    expect(composeOwnerWhere(emptyFilterModel())).toBe('');
  });

  it('multi-state selection is an OR (list overlap)', () => {
    expect(composeOwnerWhere(model({ states: ['AR', 'MT'] }))).toBe(
      "list_has_any(states, ['AR', 'MT'])",
    );
  });

  it('builds IN clauses for scalar categorical fields', () => {
    expect(composeOwnerWhere(model({ distressTiers: ['distressed', 'at-risk'] }))).toBe(
      "distress_tier IN ('distressed', 'at-risk')",
    );
    expect(composeOwnerWhere(model({ ownerKinds: ['llc'] }))).toBe("owner_kind IN ('llc')");
  });

  it('county + structure-type are list overlaps (OR)', () => {
    expect(composeOwnerWhere(model({ countyFips: ['05119', '12099'] }))).toBe(
      "list_has_any(counties, ['05119', '12099'])",
    );
    expect(composeOwnerWhere(model({ structureTypes: ['tower'] }))).toBe(
      "list_has_any(structure_types, ['tower'])",
    );
  });

  it('emits boolean / active-only columns', () => {
    expect(composeOwnerWhere(model({ inOz: true, persistentPoverty: true }))).toBe(
      'in_oz AND persistent_poverty',
    );
    expect(composeOwnerWhere(model({ activeOnly: true }))).toBe('active_tower_count > 0');
  });

  it('the score control is a minimum threshold', () => {
    expect(composeOwnerWhere(model({ scoreMin: 0.5 }))).toBe('score >= 0.5');
  });

  it('emits the other min thresholds', () => {
    expect(composeOwnerWhere(model({ portfolioMin: 3 }))).toBe('parcel_count >= 3');
    expect(composeOwnerWhere(model({ heightMin: 60 }))).toBe('tallest_tower_height_m >= 60');
    expect(composeOwnerWhere(model({ structureCountMin: 2 }))).toBe('structure_count >= 2');
  });

  it('emits a bounded range for assessed value (range bounds)', () => {
    expect(composeOwnerWhere(model({ assessedValue: [1000, 50000] }))).toBe(
      'total_assessed_value BETWEEN 1000 AND 50000',
    );
  });

  it('ignores no-op sentinel values', () => {
    // scoreMin/heightMin 0 and portfolioMin/structureCountMin 1 mean "no constraint".
    expect(
      composeOwnerWhere(
        model({ scoreMin: 0, heightMin: 0, portfolioMin: 1, structureCountMin: 1 }),
      ),
    ).toBe('');
  });

  it('escapes string literals (no injection from owner search → kind list)', () => {
    expect(composeOwnerWhere(model({ ownerKinds: ["O'BRIEN"] }))).toBe(
      "owner_kind IN ('O''BRIEN')",
    );
  });

  it('AND-joins a compound filter in a fixed order', () => {
    const where = composeOwnerWhere(
      model({
        states: ['AR', 'MT'],
        distressTiers: ['distressed'],
        ownerKinds: ['llc'],
        activeOnly: true,
        scoreMin: 0.7,
        assessedValue: [1000, 50000],
      }),
    );
    expect(where).toBe(
      "list_has_any(states, ['AR', 'MT']) AND distress_tier IN ('distressed') AND " +
        "owner_kind IN ('llc') AND active_tower_count > 0 AND score >= 0.7 AND " +
        'total_assessed_value BETWEEN 1000 AND 50000',
    );
  });

  it('throws rather than emit a non-finite number', () => {
    expect(() => composeOwnerWhere(model({ scoreMin: Infinity }))).toThrow();
    expect(() => composeOwnerWhere(model({ assessedValue: [NaN, 1] }))).toThrow();
  });
});

describe('matchesOwner — the runtime predicate', () => {
  it('an empty model matches every owner', () => {
    expect(matchesOwner(owner(), emptyFilterModel())).toBe(true);
    expect(matchesOwner(owner({ states: ['WV'], score: 0 }), emptyFilterModel())).toBe(true);
  });

  it('multi-state is OR — any overlapping state passes', () => {
    const m = model({ states: ['AR', 'MT'] });
    expect(matchesOwner(owner({ states: ['MT', 'FL'] }), m)).toBe(true); // overlaps MT
    expect(matchesOwner(owner({ states: ['FL'] }), m)).toBe(false); // disjoint
  });

  it('score is a minimum threshold (inclusive)', () => {
    expect(matchesOwner(owner({ score: 0.5 }), model({ scoreMin: 0.5 }))).toBe(true);
    expect(matchesOwner(owner({ score: 0.49 }), model({ scoreMin: 0.5 }))).toBe(false);
  });

  it('assessed value respects both bounds', () => {
    const m = model({ assessedValue: [1000, 50000] });
    expect(matchesOwner(owner({ total_assessed_value: 25000 }), m)).toBe(true);
    expect(matchesOwner(owner({ total_assessed_value: 999 }), m)).toBe(false);
    expect(matchesOwner(owner({ total_assessed_value: 50001 }), m)).toBe(false);
  });

  it('structure type is a list overlap; active-only needs a live tower', () => {
    expect(matchesOwner(owner({ structure_types: ['solar'] }), model({ structureTypes: ['tower'] }))).toBe(false);
    expect(matchesOwner(owner({ structure_types: ['tower'] }), model({ structureTypes: ['tower'] }))).toBe(true);
    expect(matchesOwner(owner({ active_tower_count: 0 }), model({ activeOnly: true }))).toBe(false);
  });

  it('a null tower height fails a positive height minimum', () => {
    expect(matchesOwner(owner({ tallest_tower_height_m: null }), model({ heightMin: 60 }))).toBe(false);
    expect(matchesOwner(owner({ tallest_tower_height_m: null }), model({ heightMin: 0 }))).toBe(true);
  });

  it('a compound filter ANDs every active clause', () => {
    const m = model({ ownerKinds: ['llc'], distressTiers: ['distressed'], scoreMin: 0.7 });
    expect(matchesOwner(owner(), m)).toBe(true);
    expect(matchesOwner(owner({ owner_kind: 'trust' }), m)).toBe(false);
  });
});

describe('registry bookkeeping', () => {
  it('isAnyFilterActive / activeFilterCount track active fields', () => {
    expect(isAnyFilterActive(emptyFilterModel())).toBe(false);
    expect(activeFilterCount(emptyFilterModel())).toBe(0);
    expect(activeFilterCount(model({ states: ['AR'], inOz: true }))).toBe(2);
  });

  it('every FilterModel key is owned by exactly one field spec', () => {
    const keys = Object.keys(emptyFilterModel()).sort();
    const owned = FILTER_FIELDS.map((f) => f.id as string).sort();
    expect(owned).toEqual(keys);
  });

  it('SQL presence and predicate activeness agree per field', () => {
    // For each field, an active model emits SQL and a no-op model does not —
    // the projection (SQL) and the runtime gate (isActive) never disagree.
    const active: FilterModel = model({
      states: ['AR'],
      distressTiers: ['distressed'],
      ownerKinds: ['llc'],
      countyFips: ['05119'],
      structureTypes: ['tower'],
      inOz: true,
      inQct: true,
      persistentPoverty: true,
      activeOnly: true,
      scoreMin: 0.5,
      portfolioMin: 2,
      heightMin: 10,
      structureCountMin: 2,
      assessedValue: [1, 2],
    });
    for (const f of FILTER_FIELDS) {
      expect(f.isActive(active)).toBe(true);
      expect(f.toSQL(active)).not.toBeNull();
      expect(f.isActive(emptyFilterModel())).toBe(false);
      expect(f.toSQL(emptyFilterModel())).toBeNull();
    }
  });
});

describe('filter-default snapshot (PRD #121)', () => {
  it('round-trips a populated model through serialize → deserialize', () => {
    const original = model({
      states: ['AR', 'MT'],
      distressTiers: ['distressed'],
      inOz: true,
      scoreMin: 0.7,
      assessedValue: [1000, 50000],
      structureCountMin: 3,
    });
    const restored = deserializeFilterModel(serializeFilterModel(original));
    expect(restored).toEqual(original);
  });

  it('round-trips the empty model (snapshotting "no filters")', () => {
    const restored = deserializeFilterModel(serializeFilterModel(emptyFilterModel()));
    expect(restored).toEqual(emptyFilterModel());
  });

  it('only serialises the fields that differ from the defaults', () => {
    const snapshot = JSON.parse(serializeFilterModel(model({ states: ['AR'] })));
    expect(snapshot).toEqual({ states: ['AR'] });
  });

  it('merges a partial snapshot onto the defaults (forward-compatible)', () => {
    const restored = deserializeFilterModel('{"scoreMin":0.5}');
    expect(restored).toEqual(model({ scoreMin: 0.5 }));
  });

  it('falls back to the empty model on malformed JSON', () => {
    expect(deserializeFilterModel('not json')).toEqual(emptyFilterModel());
    expect(deserializeFilterModel('[1,2,3]')).toEqual(emptyFilterModel());
  });

  it('applies the default only when apply is on AND the URL carries no filters', () => {
    // a shared deep link (filters in the URL) must win over a personal default
    expect(shouldApplyFilterDefault(true, true)).toBe(false);
    expect(shouldApplyFilterDefault(false, true)).toBe(true);
    expect(shouldApplyFilterDefault(false, false)).toBe(false);
    expect(shouldApplyFilterDefault(true, false)).toBe(false);
  });

  it('summarises the active filters in readable lines', () => {
    expect(summarizeFilterModel(emptyFilterModel())).toEqual([]);
    expect(
      summarizeFilterModel(model({ states: ['AR', 'MT'], scoreMin: 0.7, inOz: true })),
    ).toEqual(['States: AR, MT', 'In Opportunity Zone', 'Score ≥ 0.7']);
  });
});
