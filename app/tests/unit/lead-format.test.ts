import { describe, it, expect } from 'vitest';
import { statusGlyph, statusVar } from '../../src/lib/lead-format';
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
