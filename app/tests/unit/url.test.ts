import { describe, it, expect } from 'vitest';
import { readUrlState } from '../../src/lib/url';

describe('readUrlState', () => {
  it('reads state, selected, and reports filter presence', () => {
    const s = readUrlState(
      '?state=05&selected=P-1&filters=' + encodeURIComponent('{"hasTower":true}'),
    );
    expect(s.state).toBe('05');
    expect(s.selected).toBe('P-1');
    expect(s.hasFilters).toBe(true);
  });

  it('reports no filters when the param is absent', () => {
    expect(readUrlState('?state=05')).toEqual({ state: '05', selected: null, hasFilters: false });
  });

  it('returns nulls/false for an empty query string', () => {
    expect(readUrlState('')).toEqual({ state: null, selected: null, hasFilters: false });
  });
});
