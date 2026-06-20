import { describe, it, expect } from 'vitest';
import { trustBadge, whereFrom, howCurrent } from '../../src/lib/catalog-language';

describe('trustBadge', () => {
  it('maps each confidence value to its label + tone', () => {
    expect(trustBadge('high')).toEqual({ label: 'High', tone: 'good' });
    expect(trustBadge('medium')).toEqual({ label: 'Medium', tone: 'warn' });
    expect(trustBadge('low')).toEqual({ label: 'Low', tone: 'bad' });
  });
  it('degrades an unknown value to a neutral (muted) badge without throwing', () => {
    expect(trustBadge('provisional')).toEqual({ label: 'Provisional', tone: 'muted' });
    expect(trustBadge('not_yet_rated')).toEqual({ label: 'Not yet rated', tone: 'muted' });
    expect(trustBadge('')).toEqual({ label: 'Unknown', tone: 'muted' });
  });
});

describe('whereFrom', () => {
  it('maps each upstream_origin value to its plain phrase', () => {
    expect(whereFrom('measured')).toBe('Surveyed / measured');
    expect(whereFrom('official_filing')).toBe('Official record');
    expect(whereFrom('self_reported')).toBe('Owner-reported');
    expect(whereFrom('hand_keyed')).toBe('Hand-entered by a clerk');
    expect(whereFrom('modeled')).toBe('Computed estimate');
    expect(whereFrom('unknown')).toBe('Source unknown');
  });
  it('degrades an unknown value to a humanised label without throwing', () => {
    expect(whereFrom('crowd_sourced')).toBe('Crowd sourced');
    expect(whereFrom('')).toBe('Unknown');
  });
});

describe('howCurrent', () => {
  it('maps each freshness_risk value to its plain phrase', () => {
    expect(howCurrent('low')).toBe('Stable — rarely out of date');
    expect(howCurrent('medium')).toBe('Can lag — refresh periodically');
    expect(howCurrent('high')).toBe('Likely stale — refresh needed');
    expect(howCurrent('unknown')).toBe('No date at source');
  });
  it('degrades an unknown value to a humanised label without throwing', () => {
    expect(howCurrent('real_time')).toBe('Real time');
    expect(howCurrent('')).toBe('Unknown');
  });
});
