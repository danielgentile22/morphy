import { describe, it, expect } from 'vitest';
import type { Signal } from '../../src/lib/audit-data';
import {
  stateOf,
  baseSignalId,
  emptyFilters,
  matchesFilters,
  filtersActive,
  sortSignals,
  filtersToQuery,
  filtersFromQuery,
} from '../../src/lib/signals';

function sig(partial: Partial<Signal> & { id: string }): Signal {
  return {
    id: partial.id,
    card: partial.card ?? 'T-04',
    surface: partial.surface ?? 'panel: x',
    priority: partial.priority ?? 'P1',
    tags: {
      upstream_origin: 'official_filing',
      freshness_risk: 'low',
      derivation_risk: 'low',
      verifiability: 'per_instance_checkable',
      confidence: 'high',
      ...partial.tags,
    },
    verdict: partial.verdict ?? 'verdict text',
    dossier: partial.dossier ?? 'parcels-FL.md#x',
  };
}

describe('stateOf / baseSignalId', () => {
  it('derives FIPS from the @NN suffix', () => {
    expect(stateOf('owner_name@12')).toBe('12');
    expect(stateOf('parcel_id@05')).toBe('05');
  });
  it('returns null for national signals', () => {
    expect(stateOf('tower_coords')).toBeNull();
    expect(stateOf('carriers')).toBeNull();
  });
  it('ignores an unknown FIPS suffix', () => {
    expect(stateOf('foo@99')).toBeNull();
  });
  it('strips the suffix for the base id', () => {
    expect(baseSignalId('owner_name@12')).toBe('owner_name');
    expect(baseSignalId('tower_coords')).toBe('tower_coords');
  });
});

describe('matchesFilters', () => {
  const s = sig({ id: 'owner_name@12', card: 'T-04', tags: { confidence: 'high' } as Signal['tags'] });

  it('passes when no filters are set', () => {
    expect(matchesFilters(s, emptyFilters())).toBe(true);
  });
  it('filters by confidence', () => {
    expect(matchesFilters(s, { ...emptyFilters(), confidence: ['low'] })).toBe(false);
    expect(matchesFilters(s, { ...emptyFilters(), confidence: ['high'] })).toBe(true);
  });
  it('filters by state via the id suffix', () => {
    expect(matchesFilters(s, { ...emptyFilters(), state: ['12'] })).toBe(true);
    expect(matchesFilters(s, { ...emptyFilters(), state: ['05'] })).toBe(false);
  });
  it('matches national pseudo-state for unsuffixed ids', () => {
    const nat = sig({ id: 'tower_coords' });
    expect(matchesFilters(nat, { ...emptyFilters(), state: ['national'] })).toBe(true);
    expect(matchesFilters(nat, { ...emptyFilters(), state: ['12'] })).toBe(false);
  });
  it('searches id/surface/verdict text case-insensitively', () => {
    expect(matchesFilters(s, { ...emptyFilters(), text: 'OWNER' })).toBe(true);
    expect(matchesFilters(s, { ...emptyFilters(), text: 'nonexistent' })).toBe(false);
  });
  it('ANDs across dimensions', () => {
    expect(matchesFilters(s, { ...emptyFilters(), confidence: ['high'], state: ['05'] })).toBe(false);
  });
});

describe('filtersActive', () => {
  it('is false for empty filters and true once anything is set', () => {
    expect(filtersActive(emptyFilters())).toBe(false);
    expect(filtersActive({ ...emptyFilters(), confidence: ['low'] })).toBe(true);
    expect(filtersActive({ ...emptyFilters(), text: 'x' })).toBe(true);
  });
});

describe('sortSignals', () => {
  const a = sig({ id: 'a', tags: { confidence: 'high' } as Signal['tags'] });
  const b = sig({ id: 'b', tags: { confidence: 'low' } as Signal['tags'] });
  const c = sig({ id: 'c', tags: { confidence: 'medium' } as Signal['tags'] });

  it('sorts weakest-first by confidence ascending', () => {
    const out = sortSignals([a, b, c], 'confidence', true).map((s) => s.id);
    expect(out).toEqual(['b', 'c', 'a']); // low, medium, high
  });
  it('reverses on descending', () => {
    const out = sortSignals([a, b, c], 'confidence', false).map((s) => s.id);
    expect(out).toEqual(['a', 'c', 'b']);
  });
  it('does not mutate the input', () => {
    const input = [a, b, c];
    sortSignals(input, 'id', true);
    expect(input.map((s) => s.id)).toEqual(['a', 'b', 'c']);
  });
});

describe('filters ⇄ query round-trip', () => {
  it('encodes only non-empty facets', () => {
    expect(filtersToQuery(emptyFilters())).toBe('');
    const f = { ...emptyFilters(), confidence: ['low', 'medium'], state: ['12'], text: 'owner' };
    const q = filtersToQuery(f);
    expect(q).toContain('conf=low%2Cmedium');
    expect(q).toContain('state=12');
    expect(q).toContain('q=owner');
  });
  it('round-trips through the query string', () => {
    const f = { ...emptyFilters(), confidence: ['low'], derivation_risk: ['high'], text: 'join' };
    const back = filtersFromQuery(filtersToQuery(f));
    expect(back.confidence).toEqual(['low']);
    expect(back.derivation_risk).toEqual(['high']);
    expect(back.text).toBe('join');
    expect(back.state).toEqual([]);
  });
});
