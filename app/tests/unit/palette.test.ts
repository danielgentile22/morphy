import { describe, it, expect } from 'vitest';
import {
  WONG,
  DISTRESS_TIERS,
  distressTierColor,
  distressTierLabel,
  overlayTypeColor,
  overlayTypeLabel,
  ownerKindLabel,
  layerColor,
  TOWER_MARKER_SVG,
} from '../../src/lib/palette';

describe('WONG palette', () => {
  it('has eight colourblind-safe hues', () => {
    expect(Object.keys(WONG)).toHaveLength(8);
    for (const hex of Object.values(WONG)) {
      expect(hex).toMatch(/^#[0-9a-f]{6}$/);
    }
  });
});

describe('distress tier', () => {
  it('maps every known tier to a distinct colour', () => {
    const colors = DISTRESS_TIERS.map(distressTierColor);
    expect(new Set(colors).size).toBe(DISTRESS_TIERS.length);
  });
  it('falls back to neutral for an unknown tier', () => {
    expect(distressTierColor('')).toBe(distressTierColor('bogus'));
    expect(distressTierColor('distressed')).not.toBe(distressTierColor('bogus'));
  });
  it('labels tiers for display', () => {
    expect(distressTierLabel('at-risk')).toBe('At-risk');
    expect(distressTierLabel('distressed')).toBe('Distressed');
    expect(distressTierLabel('')).toBe('Unknown');
  });
});

describe('overlay type', () => {
  it('colours the known overlay types distinctly', () => {
    expect(overlayTypeColor('opportunity_zone')).not.toBe(overlayTypeColor('qct'));
  });
  it('labels overlay types', () => {
    expect(overlayTypeLabel('opportunity_zone')).toBe('Opportunity Zone');
    expect(overlayTypeLabel('qct')).toBe('Qualified Census Tract');
  });
  it('humanises an unknown overlay type instead of crashing', () => {
    expect(overlayTypeLabel('some_new_type')).toBe('some new type');
  });
});

describe('ownerKindLabel', () => {
  it('upper-cases the LLC acronym', () => {
    expect(ownerKindLabel('llc')).toBe('LLC');
  });
  it('title-cases the other kinds', () => {
    expect(ownerKindLabel('trust')).toBe('Trust');
    expect(ownerKindLabel('corporation')).toBe('Corporation');
  });
  it('handles unknown / blank input', () => {
    expect(ownerKindLabel('')).toBe('Unknown');
    expect(ownerKindLabel(null)).toBe('Unknown');
  });
});

describe('layerColor', () => {
  it('returns a colour for known layers and views', () => {
    expect(layerColor('towers')).toMatch(/^#[0-9a-f]{6}$/i);
    expect(layerColor('interestingness_top_1000')).toMatch(/^#[0-9a-f]{6}$/i);
  });
  it('falls back for an unknown layer', () => {
    expect(layerColor('made_up_layer')).toMatch(/^#[0-9a-f]{6}$/i);
  });
});

describe('TOWER_MARKER_SVG', () => {
  it('is a self-contained SVG', () => {
    expect(TOWER_MARKER_SVG).toContain('<svg');
    expect(TOWER_MARKER_SVG).toContain('</svg>');
    expect(TOWER_MARKER_SVG).toContain('xmlns');
  });
});
