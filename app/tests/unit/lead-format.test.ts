import { describe, it, expect } from 'vitest';
import { mailingLine, statusGlyph, statusVar } from '../../src/lib/lead-format';
import { STATUSES } from '../../src/lib/lead-status';

describe('statusGlyph — the colorblind non-color cue (PRD #121)', () => {
  it('gives every status a distinct glyph', () => {
    const glyphs = STATUSES.map(statusGlyph);
    expect(new Set(glyphs).size).toBe(STATUSES.length);
  });

  it('marks the won/lost pair with a ✓ / ✗ contrast', () => {
    expect(statusGlyph('in_business')).toBe('✓');
    expect(statusGlyph('uninterested')).toBe('✗');
  });

  it('falls back to a neutral bullet for an unknown status', () => {
    expect(statusGlyph('whatever')).toBe('•');
  });
});

describe('statusVar', () => {
  it('maps a status to its CSS custom property', () => {
    expect(statusVar('in_business')).toBe('var(--s-in_business)');
  });
});

describe('mailingLine', () => {
  it('joins the parts of a split address', () => {
    expect(mailingLine({ addr: '12 MAIN ST', city: 'HELENA', state: 'MT', zip: '59601' })).toBe(
      '12 MAIN ST, HELENA, MT 59601',
    );
  });

  it('does not repeat parts a source already packed into addr', () => {
    expect(
      mailingLine({
        addr: 'PO BOX 1517, BLUEFIELD, WV 24701',
        city: 'BLUEFIELD',
        state: 'WV',
        zip: '24701',
      }),
    ).toBe('PO BOX 1517, BLUEFIELD, WV 24701');
  });

  it('skips missing parts', () => {
    expect(mailingLine({ addr: '12 MAIN ST', city: null, state: 'AR', zip: '' })).toBe(
      '12 MAIN ST, AR',
    );
  });
});
