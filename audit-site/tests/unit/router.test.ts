import { describe, it, expect } from 'vitest';
import { parseHash, hrefs } from '../../src/lib/router.svelte';

describe('parseHash', () => {
  it('defaults to overview', () => {
    expect(parseHash('')).toEqual({ name: 'overview' });
    expect(parseHash('#/')).toEqual({ name: 'overview' });
    expect(parseHash('#/garbage')).toEqual({ name: 'overview' });
  });
  it('parses the catalog list and a group anchor', () => {
    expect(parseHash('#/catalog')).toEqual({ name: 'catalog', anchor: null });
    expect(parseHash('#/catalog/landowner')).toEqual({ name: 'catalog', anchor: 'landowner' });
  });
  it('parses the freshness placeholder route', () => {
    expect(parseHash('#/freshness')).toEqual({ name: 'freshness' });
  });
  it('parses the signals list and its query', () => {
    expect(parseHash('#/signals')).toEqual({ name: 'signals', query: '' });
    expect(parseHash('#/signals?conf=low&state=12')).toEqual({ name: 'signals', query: 'conf=low&state=12' });
  });
  it('parses a signal detail, decoding the id', () => {
    expect(parseHash('#/signals/owner_name%4012')).toEqual({ name: 'signal', id: 'owner_name@12' });
    expect(parseHash('#/signals/tower_coords')).toEqual({ name: 'signal', id: 'tower_coords' });
  });
  it('parses cards and card detail', () => {
    expect(parseHash('#/cards')).toEqual({ name: 'cards' });
    expect(parseHash('#/cards/T-08')).toEqual({ name: 'card', id: 'T-08' });
  });
  it('parses doc routes with and without an anchor', () => {
    expect(parseHash('#/doc/INDEX.md')).toEqual({ name: 'doc', file: 'INDEX.md', anchor: null });
    expect(parseHash('#/doc/fcc-asr.md/tower_height')).toEqual({
      name: 'doc',
      file: 'fcc-asr.md',
      anchor: 'tower_height',
    });
  });
});

describe('hrefs', () => {
  it('builds round-trippable hrefs', () => {
    expect(hrefs.signal('owner_name@12')).toBe('#/signals/owner_name%4012');
    expect(parseHash(hrefs.signal('owner_name@12'))).toEqual({ name: 'signal', id: 'owner_name@12' });
    expect(hrefs.card('T-08')).toBe('#/cards/T-08');
    expect(hrefs.doc('fcc-asr.md', 'tower_height')).toBe('#/doc/fcc-asr.md/tower_height');
    expect(hrefs.signals('conf=low')).toBe('#/signals?conf=low');
    expect(hrefs.signals()).toBe('#/signals');
    expect(hrefs.catalog()).toBe('#/catalog');
    expect(hrefs.catalog('landowner')).toBe('#/catalog/landowner');
    expect(parseHash(hrefs.catalog('landowner'))).toEqual({ name: 'catalog', anchor: 'landowner' });
    expect(hrefs.freshness).toBe('#/freshness');
    expect(parseHash(hrefs.freshness)).toEqual({ name: 'freshness' });
  });
});
