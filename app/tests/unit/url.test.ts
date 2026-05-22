import { describe, it, expect } from 'vitest';
import { emptyFilters } from '../../src/lib/filters';
import { encodeFilters, decodeFilters, readUrlState, buildUrl } from '../../src/lib/url';

describe('encodeFilters / decodeFilters', () => {
  it('an empty filter encodes to {}', () => {
    expect(encodeFilters(emptyFilters())).toBe('{}');
  });

  it('encodes only the non-default fields', () => {
    const encoded = encodeFilters({ ...emptyFilters(), ownerKind: ['llc'], hasTower: true });
    expect(JSON.parse(encoded)).toEqual({ ownerKind: ['llc'], hasTower: true });
  });

  it('round-trips a filter state', () => {
    const filters = {
      ...emptyFilters(),
      ownerKind: ['llc', 'trust'],
      distressTier: ['distressed'],
      scoreMin: 0.6,
      inOz: true,
    };
    expect(decodeFilters(encodeFilters(filters))).toEqual(filters);
  });

  it('tolerates a malformed filters param', () => {
    expect(decodeFilters('not json')).toEqual(emptyFilters());
    expect(decodeFilters('[1,2,3]')).toEqual(emptyFilters());
  });

  it('ignores unknown keys from a hand-crafted URL', () => {
    const decoded = decodeFilters('{"ownerKind":["llc"],"evil":"x"}');
    expect(decoded.ownerKind).toEqual(['llc']);
    expect('evil' in decoded).toBe(false);
  });
});

describe('readUrlState', () => {
  it('reads state, selected, and filters', () => {
    const s = readUrlState('?state=05&selected=P-1&filters=' + encodeURIComponent('{"hasTower":true}'));
    expect(s.state).toBe('05');
    expect(s.selected).toBe('P-1');
    expect(s.filters?.hasTower).toBe(true);
  });

  it('returns nulls for an empty query string', () => {
    expect(readUrlState('')).toEqual({ state: null, selected: null, filters: null });
  });
});

describe('buildUrl', () => {
  it('is a bare path when nothing is set', () => {
    expect(buildUrl('/app/', null, null, emptyFilters())).toBe('/app/');
  });

  it('includes state, selected, and active filters', () => {
    const url = buildUrl('/app/', '05', 'P-9', { ...emptyFilters(), hasSolar: true });
    expect(url).toContain('state=05');
    expect(url).toContain('selected=P-9');
    expect(url).toContain('filters=');
  });

  it('omits the filters param for an unfiltered view', () => {
    expect(buildUrl('/app/', '30', null, emptyFilters())).toBe('/app/?state=30');
  });

  it('round-trips through readUrlState', () => {
    const filters = { ...emptyFilters(), ownerKind: ['llc'], scoreMin: 0.5 };
    const url = buildUrl('/app/', '05', 'APN-7', filters);
    const back = readUrlState(url.slice(url.indexOf('?')));
    expect(back.state).toBe('05');
    expect(back.selected).toBe('APN-7');
    expect(back.filters).toEqual(filters);
  });
});
