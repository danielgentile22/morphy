import { describe, it, expect } from 'vitest';
import {
  scoreOwner,
  features,
  zeroWeights,
  effectiveScore,
  shouldApplyTeamDefault,
  defaultConfig,
  DEFAULT_WEIGHTS,
  type ScorableOwner,
  type ScoreExtents,
} from '../../src/lib/scoring';

const EXT: ScoreExtents = {
  assessedMax: 1000,
  portfolioMax: 10,
  towerMax: 20,
  heightMax: 100,
  carrierMax: 4,
};

function owner(over: Partial<ScorableOwner> = {}): ScorableOwner {
  return {
    distress_tier: '',
    in_oz: false,
    in_qct: false,
    persistent_poverty: false,
    total_assessed_value: 0,
    parcel_count: 1,
    tower_count: 0,
    active_tower_count: 0,
    tallest_tower_height_m: null,
    carrier_count: 0,
    ...over,
  };
}

describe('scoring engine (UI overhaul P4 / #114)', () => {
  it('normalizes each feature to [0,1]', () => {
    const f = features(
      owner({
        distress_tier: 'distressed',
        in_oz: true,
        total_assessed_value: 500,
        parcel_count: 5,
        tower_count: 10,
        tallest_tower_height_m: 50,
        active_tower_count: 2,
      }),
      EXT,
    );
    expect(f.distress).toBe(1); // distressed = rank 3 / 3
    expect(f.oz).toBe(1);
    expect(f.qct).toBe(0);
    expect(f.assessedValue).toBe(0.5);
    expect(f.portfolio).toBe(0.5);
    expect(f.towers).toBe(0.5);
    expect(f.height).toBe(0.5);
    expect(f.active).toBe(1);
  });

  it('ADR-073 thesis features invert portfolio/value and reward carriers', () => {
    const f = features(
      owner({ parcel_count: 5, total_assessed_value: 500, carrier_count: 2 }),
      EXT,
    );
    // smallPortfolio / lowValue are the inverse of portfolio / assessedValue.
    expect(f.portfolio).toBe(0.5);
    expect(f.smallPortfolio).toBe(0.5);
    expect(f.assessedValue).toBe(0.5);
    expect(f.lowValue).toBe(0.5);
    // carriers rewards more carriers on the best tower (2 / carrierMax 4).
    expect(f.carriers).toBe(0.5);
    // A tiny, cheap, well-tenanted owner scores high; a giant expensive one low.
    const small = owner({ parcel_count: 1, total_assessed_value: 0, carrier_count: 4 });
    const giant = owner({ parcel_count: 10, total_assessed_value: 1000, carrier_count: 0 });
    expect(scoreOwner(small, DEFAULT_WEIGHTS, EXT)).toBeGreaterThan(
      scoreOwner(giant, DEFAULT_WEIGHTS, EXT),
    );
  });

  it('DEFAULT_WEIGHTS is a valid preset (all features present, sums to 1)', () => {
    const keys = Object.keys(zeroWeights());
    for (const k of keys) expect(DEFAULT_WEIGHTS).toHaveProperty(k);
    const sum = Object.values(DEFAULT_WEIGHTS).reduce((a, b) => a + b, 0);
    expect(sum).toBeCloseTo(1, 6);
  });

  it('weights × features sums to a score', () => {
    // distress weight 1, all else 0 → score == distress feature.
    const w = { ...zeroWeights(), distress: 1 };
    expect(scoreOwner(owner({ distress_tier: 'at-risk' }), w, EXT)).toBeCloseTo(2 / 3, 3);
    expect(scoreOwner(owner({ distress_tier: 'distressed' }), w, EXT)).toBe(1);
    // a tunable blend
    const blend = { ...zeroWeights(), oz: 0.5, distress: 0.5 };
    expect(scoreOwner(owner({ in_oz: true, distress_tier: 'distressed' }), blend, EXT)).toBe(1);
  });

  it('all-zero weights → zero score', () => {
    expect(scoreOwner(owner({ distress_tier: 'distressed', in_oz: true }), zeroWeights(), EXT)).toBe(
      0,
    );
  });

  it('changing a weight changes the ranking', () => {
    const a = owner({ distress_tier: 'distressed' }); // high distress, no OZ
    const b = owner({ in_oz: true }); // OZ, no distress
    const distressFirst = { ...zeroWeights(), distress: 1, oz: 0.1 };
    const ozFirst = { ...zeroWeights(), distress: 0.1, oz: 1 };
    expect(scoreOwner(a, distressFirst, EXT)).toBeGreaterThan(scoreOwner(b, distressFirst, EXT));
    // flip the weights → the ranking flips
    expect(scoreOwner(b, ozFirst, EXT)).toBeGreaterThan(scoreOwner(a, ozFirst, EXT));
  });

  it('default weights produce a positive score for an interesting owner', () => {
    const s = scoreOwner(
      owner({ distress_tier: 'distressed', in_oz: true, tower_count: 10 }),
      DEFAULT_WEIGHTS,
      EXT,
    );
    expect(s).toBeGreaterThan(0);
  });

  it('default config = baked interestingness (no regression) (#114)', () => {
    // useDefault → effectiveScore IS the baked `score`, ignoring weights/extents,
    // so the default ordering reproduces the precompute exactly.
    const cfg = defaultConfig();
    expect(cfg.useDefault).toBe(true);
    expect(cfg.weights).toEqual(DEFAULT_WEIGHTS);
    const o = { ...owner({ distress_tier: 'distressed', in_oz: true }), score: 0.42 };
    expect(effectiveScore(o, cfg, EXT)).toBe(0.42);
    // a higher baked score still ranks above a lower one under the default
    const lo = { ...owner(), score: 0.1 };
    expect(effectiveScore(o, cfg, EXT)).toBeGreaterThan(effectiveScore(lo, cfg, EXT));
  });

  it('custom config = weighted blend, not the baked score (#114)', () => {
    const cfg = { useDefault: false, weights: { ...zeroWeights(), distress: 1 } };
    const o = { ...owner({ distress_tier: 'distressed' }), score: 0.01 };
    expect(effectiveScore(o, cfg, EXT)).toBe(1); // blend, not the baked 0.01
  });

  it('team default applies only when nothing active + still on baked default (#115)', () => {
    const presets = [
      { id: 1, is_default: false },
      { id: 2, is_default: true },
    ];
    // nothing active + baked default → adopt the is_default preset
    expect(shouldApplyTeamDefault(presets, null, defaultConfig())?.id).toBe(2);
    // a preset already active → never clobber it
    expect(shouldApplyTeamDefault(presets, 1, defaultConfig())).toBeNull();
    // user already on custom weights → never clobber them
    expect(shouldApplyTeamDefault(presets, null, { useDefault: false, weights: zeroWeights() })).toBeNull();
    // no default preset defined → nothing to apply
    expect(shouldApplyTeamDefault([{ id: 1, is_default: false }], null, defaultConfig())).toBeNull();
  });

  it('zero extents never divide-by-zero', () => {
    const ext: ScoreExtents = {
      assessedMax: 0,
      portfolioMax: 0,
      towerMax: 0,
      heightMax: 0,
      carrierMax: 0,
    };
    expect(() => scoreOwner(owner({ total_assessed_value: 100 }), DEFAULT_WEIGHTS, ext)).not.toThrow();
    expect(scoreOwner(owner({ total_assessed_value: 100 }), { ...zeroWeights(), assessedValue: 1 }, ext)).toBe(0);
  });
});
