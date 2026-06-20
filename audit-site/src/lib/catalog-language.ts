/**
 * M2 · Plain-language translator (deep module). Pure maps from the audit's
 * controlled vocab to co-founder-friendly strings — the human face of the
 * raw tags. Every map degrades gracefully: an unrecognised value returns a
 * neutral humanised label (never throws), so the catalog keeps rendering when
 * the vocab in `index.json` evolves (the auto-populate contract). The plain
 * meanings live in catalog-config.ts; this file only translates the vocab.
 */

/** Trust tone → the `.chip--<tone>` class (reuses the audit chip palette). */
export type TrustTone = 'good' | 'warn' | 'bad' | 'muted';

export interface TrustBadge {
  label: string;
  tone: TrustTone;
}

/** `confidence → Trust badge`. 1:1 with the audit's holistic confidence call —
 *  no new composite score is invented. Unknown values degrade to a neutral
 *  (muted) badge rather than guessing a tone. */
const TRUST: Record<string, TrustBadge> = {
  high: { label: 'High', tone: 'good' },
  medium: { label: 'Medium', tone: 'warn' },
  low: { label: 'Low', tone: 'bad' },
};

export function trustBadge(confidence: string): TrustBadge {
  return TRUST[confidence] ?? { label: humanize(confidence), tone: 'muted' };
}

/** `upstream_origin → where-from phrase`. */
const WHERE_FROM: Record<string, string> = {
  measured: 'Surveyed / measured',
  official_filing: 'Official record',
  self_reported: 'Owner-reported',
  hand_keyed: 'Hand-entered by a clerk',
  modeled: 'Computed estimate',
  unknown: 'Source unknown',
};

export function whereFrom(upstreamOrigin: string): string {
  return WHERE_FROM[upstreamOrigin] ?? humanize(upstreamOrigin);
}

/** `freshness_risk → how-current phrase`. */
const HOW_CURRENT: Record<string, string> = {
  low: 'Stable — rarely out of date',
  medium: 'Can lag — refresh periodically',
  high: 'Likely stale — refresh needed',
  unknown: 'No date at source',
};

export function howCurrent(freshnessRisk: string): string {
  return HOW_CURRENT[freshnessRisk] ?? humanize(freshnessRisk);
}

/** Neutral fallback: `some_value` → `Some value`; empty → `Unknown`. */
function humanize(value: string): string {
  if (!value) return 'Unknown';
  const s = value.replace(/_/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}
