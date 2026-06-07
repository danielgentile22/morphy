/**
 * Tunable interestingness scoring (UI overhaul P4 / #114, ADR-058 amended).
 *
 * The score is no longer a fixed formula: the user weights a menu of features
 * and Explore re-ranks live. Two modes (a `ScoringConfig`):
 *   - `useDefault: true`  → rank by the baked interestingness `score` (the
 *     precompute's default profile). This reproduces today's ordering exactly —
 *     no regression — and is the default.
 *   - custom weights      → `scoreOwner(owner, weights, extents)`: a weighted
 *     blend over normalized owner features, recomputed in the browser on every
 *     weight change (cheap over the in-memory owners index — no DuckDB needed).
 *
 * #115 layers named, tenant-shared presets on top of this config. Ranking is
 * owner-grained: one `effectiveScore` per owner (baked when default, else the
 * weighted blend) drives BOTH Explore's tower list (projected onto each of the
 * owner's towers) AND the owner worklist (Leads / MyLeads) — so switching a
 * preset re-ranks every surface consistently.
 */

const TIER_RANK: Record<string, number> = {
  '': 0,
  transitional: 1,
  'at-risk': 2,
  distressed: 3,
};

/** The weightable feature menu. Each weight is 0..1; 0 = ignore the feature. */
export interface ScoreWeights {
  distress: number; // ARC tier severity
  oz: number; // Opportunity Zone
  qct: number; // Qualified Census Tract
  poverty: number; // persistent poverty
  assessedValue: number; // total assessed value
  portfolio: number; // parcel_count (portfolio size)
  towers: number; // tower_count
  height: number; // tallest tower
  active: number; // has an active tower
}

export const SCORE_FEATURES: { key: keyof ScoreWeights; label: string }[] = [
  { key: 'distress', label: 'Distress tier' },
  { key: 'oz', label: 'Opportunity Zone' },
  { key: 'qct', label: 'Qualified Census Tract' },
  { key: 'poverty', label: 'Persistent poverty' },
  { key: 'assessedValue', label: 'Assessed value' },
  { key: 'portfolio', label: 'Portfolio size' },
  { key: 'towers', label: 'Tower count' },
  { key: 'height', label: 'Tallest tower' },
  { key: 'active', label: 'Active tower' },
];

/** A sensible starting point when the user switches to custom weights. */
export const DEFAULT_WEIGHTS: ScoreWeights = {
  distress: 0.3,
  oz: 0.15,
  qct: 0.1,
  poverty: 0.1,
  assessedValue: 0.1,
  portfolio: 0.1,
  towers: 0.1,
  height: 0.05,
  active: 0.05,
};

export function zeroWeights(): ScoreWeights {
  return {
    distress: 0,
    oz: 0,
    qct: 0,
    poverty: 0,
    assessedValue: 0,
    portfolio: 0,
    towers: 0,
    height: 0,
    active: 0,
  };
}

/** Normalization extents (the max of each numeric feature across the index). */
export interface ScoreExtents {
  assessedMax: number;
  portfolioMax: number;
  towerMax: number;
  heightMax: number;
}

/** The owner fields the scorer reads. */
export interface ScorableOwner {
  distress_tier: string;
  in_oz: boolean;
  in_qct: boolean;
  persistent_poverty: boolean;
  total_assessed_value: number;
  parcel_count: number;
  tower_count: number;
  active_tower_count: number;
  tallest_tower_height_m: number | null;
}

function norm(value: number, max: number): number {
  return max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
}

/** Each feature normalized to [0,1] for the given owner + extents. */
export function features(o: ScorableOwner, ext: ScoreExtents): ScoreWeights {
  return {
    distress: (TIER_RANK[o.distress_tier] ?? 0) / 3,
    oz: o.in_oz ? 1 : 0,
    qct: o.in_qct ? 1 : 0,
    poverty: o.persistent_poverty ? 1 : 0,
    assessedValue: norm(o.total_assessed_value, ext.assessedMax),
    portfolio: norm(o.parcel_count, ext.portfolioMax),
    towers: norm(o.tower_count, ext.towerMax),
    height: norm(o.tallest_tower_height_m ?? 0, ext.heightMax),
    active: o.active_tower_count > 0 ? 1 : 0,
  };
}

/** Weighted blend of an owner's normalized features under `weights`. Pure;
 *  ranking only needs relative order, so this is a raw weighted sum. */
export function scoreOwner(o: ScorableOwner, weights: ScoreWeights, ext: ScoreExtents): number {
  const f = features(o, ext);
  let total = 0;
  for (const k of Object.keys(weights) as (keyof ScoreWeights)[]) {
    total += weights[k] * f[k];
  }
  return Math.round(total * 10000) / 10000;
}

export interface ScoringConfig {
  useDefault: boolean;
  weights: ScoreWeights;
}

export function defaultConfig(): ScoringConfig {
  return { useDefault: true, weights: { ...DEFAULT_WEIGHTS } };
}

/** An owner's score under a config: the baked interestingness when the config
 *  is the default (no regression — reproduces today's ordering exactly), else
 *  the weighted blend. One owner-grained score per owner drives every surface
 *  (Explore towers + Leads/MyLeads worklist), so a preset switch re-ranks them
 *  all consistently (#114/#115). */
export function effectiveScore(
  o: ScorableOwner & { score: number },
  config: ScoringConfig,
  ext: ScoreExtents,
): number {
  return config.useDefault ? o.score : scoreOwner(o, config.weights, ext);
}

/** The team-default preset to auto-apply on load: only when nothing is active
 *  yet and the config is still the baked default (so it never clobbers a user's
 *  in-progress custom weights). Pure so it's testable without the runes store
 *  (#115). */
export function shouldApplyTeamDefault<P extends { is_default: boolean }>(
  presets: readonly P[],
  activePresetId: number | null,
  config: ScoringConfig,
): P | null {
  if (activePresetId !== null || !config.useDefault) return null;
  return presets.find((p) => p.is_default) ?? null;
}
