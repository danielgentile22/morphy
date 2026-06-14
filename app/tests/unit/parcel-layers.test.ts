import { describe, it, expect } from 'vitest';
import { Z_ON, parcelLayerAppearance } from '../../src/lib/parcel-layers';

/**
 * Byte-for-byte contract for the parcel zoom/opacity expressions (PRD #163 /
 * #165). Prior art: the byte-for-byte SQL assertions for `composeWhere`
 * (query.ts) and `composeOwnerWhere` (filter-model.ts). The point of pinning the
 * exact emitted MapLibre expressions is that `Z_on` is one tunable source of
 * truth — a tweak to the appearance zoom should move every threshold here in
 * lockstep, and these tests make any drift loud.
 */
describe('parcelLayerAppearance — byte-for-byte zoom/opacity contract', () => {
  it('gates fill + line on the same minzoom = Z_on (no rendering below it)', () => {
    expect(parcelLayerAppearance(12).minzoom).toBe(12);
    expect(parcelLayerAppearance(11).minzoom).toBe(11);
  });

  it('emits the crisp fill-opacity ramp (Z_on → Z_on+0.5), selected branch as the output stop', () => {
    expect(parcelLayerAppearance(12).fillOpacity).toEqual([
      'interpolate',
      ['linear'],
      ['zoom'],
      12,
      0,
      12.5,
      ['case', ['boolean', ['feature-state', 'selected'], false], 0.85, 0.55],
    ]);
  });

  it('emits the crisp line-opacity ramp (Z_on → Z_on+0.5)', () => {
    expect(parcelLayerAppearance(12).lineOpacity).toEqual([
      'interpolate',
      ['linear'],
      ['zoom'],
      12,
      0,
      12.5,
      0.85,
    ]);
  });

  it('is parameterised — a different Z_on shifts every zoom threshold in lockstep', () => {
    const a = parcelLayerAppearance(11);
    expect(a.minzoom).toBe(11);
    expect(a.fillOpacity).toEqual([
      'interpolate',
      ['linear'],
      ['zoom'],
      11,
      0,
      11.5,
      ['case', ['boolean', ['feature-state', 'selected'], false], 0.85, 0.55],
    ]);
    expect(a.lineOpacity).toEqual(['interpolate', ['linear'], ['zoom'], 11, 0, 11.5, 0.85]);
  });

  it('defaults to the pinned Z_ON when called with no argument', () => {
    const def = parcelLayerAppearance();
    const pinned = parcelLayerAppearance(Z_ON);
    expect(def).toEqual(pinned);
    expect(def.minzoom).toBe(Z_ON);
  });

  it('emits the exact expressions at the pinned Z_ON = 14 (the shipped contract)', () => {
    // The value pinned by PR #165's empirical tuning: the densest FL metro only
    // reaches 100% parcel completeness at z14 (= tile MAX_ZOOM), so 14 is where
    // parcels can appear fully complete. The tile slice (#167) must use 14 too.
    expect(Z_ON).toBe(14);
    expect(parcelLayerAppearance()).toEqual({
      minzoom: 14,
      fillOpacity: [
        'interpolate',
        ['linear'],
        ['zoom'],
        14,
        0,
        14.5,
        ['case', ['boolean', ['feature-state', 'selected'], false], 0.85, 0.55],
      ],
      lineOpacity: ['interpolate', ['linear'], ['zoom'], 14, 0, 14.5, 0.85],
    });
  });

  it('never reintroduces the pre-#165 size-graduated fade (no z8→z10 ramp)', () => {
    // The old fill ramp started at zoom 8 → fully on by 10, which let big rural
    // parcels appear well before the full set. The appearance zoom is now the
    // first stop; the old 8/10 stops must never come back.
    const fill = JSON.stringify(parcelLayerAppearance(Z_ON).fillOpacity);
    expect(fill).toContain(`["zoom"],${Z_ON},0`); // first zoom stop == Z_on
    expect(fill).not.toContain('["zoom"],8,0,10'); // not the pre-#165 ramp
  });
});
