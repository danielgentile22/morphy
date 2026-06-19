/**
 * Pure helpers over the signal set: the state a signal belongs to (derived from
 * its id suffix, never a stored field — handoff §9), and the filter/sort model
 * the Signals browser runs on. Kept pure + unit-tested; the store and the
 * browser component are the only consumers.
 */

import type { Signal, TagDimension } from './audit-data';

/** Pilot states, keyed by FIPS — the `@NN` suffix on per-state signal ids. */
export const STATE_NAMES: Record<string, string> = {
  '05': 'Arkansas',
  '12': 'Florida',
  '30': 'Montana',
  '54': 'West Virginia',
};

/** The FIPS for a per-state signal (`owner_name@12` → `12`), or null when the
 *  signal is national / cross-state (no `@NN` suffix). */
export function stateOf(signalId: string): string | null {
  const m = signalId.match(/@(\d{2})$/);
  return m && m[1] in STATE_NAMES ? m[1] : null;
}

/** A signal id with its `@NN` suffix stripped (`owner_name@12` → `owner_name`),
 *  for grouping the four per-state variants of one logical signal. */
export function baseSignalId(signalId: string): string {
  return signalId.replace(/@\d{2}$/, '');
}

/** Active filter selections. Empty array on a dimension = no constraint.
 *  Arrays (not Sets) so Svelte 5 proxies them reactively — selections are tiny
 *  (≤6 values), so `includes` is cheap. */
export interface SignalFilters {
  text: string;
  confidence: string[];
  state: string[];
  card: string[];
  priority: string[];
  upstream_origin: string[];
  freshness_risk: string[];
  derivation_risk: string[];
  verifiability: string[];
}

export function emptyFilters(): SignalFilters {
  return {
    text: '',
    confidence: [],
    state: [],
    card: [],
    priority: [],
    upstream_origin: [],
    freshness_risk: [],
    derivation_risk: [],
    verifiability: [],
  };
}

/** Tag dimensions that are also filter facets (every dimension except the ones
 *  filtered specially: confidence + the synthesized state/card/priority). */
const TAG_FACETS: TagDimension[] = [
  'upstream_origin',
  'freshness_risk',
  'derivation_risk',
  'verifiability',
];

export function matchesFilters(signal: Signal, f: SignalFilters): boolean {
  if (f.confidence.length && !f.confidence.includes(signal.tags.confidence)) return false;
  if (f.priority.length && !f.priority.includes(signal.priority ?? '—')) return false;
  if (f.card.length && !f.card.includes(signal.card)) return false;
  if (f.state.length) {
    const st = stateOf(signal.id);
    // The "national" pseudo-state matches signals with no @NN suffix.
    if (!(st ? f.state.includes(st) : f.state.includes('national'))) return false;
  }
  for (const dim of TAG_FACETS) {
    const sel = f[dim];
    if (sel.length && !sel.includes(signal.tags[dim])) return false;
  }
  if (f.text.trim()) {
    const q = f.text.trim().toLowerCase();
    const hay = `${signal.id} ${signal.card} ${signal.surface} ${signal.verdict}`.toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

export function filtersActive(f: SignalFilters): boolean {
  return (
    f.text.trim() !== '' ||
    f.confidence.length > 0 ||
    f.state.length > 0 ||
    f.card.length > 0 ||
    f.priority.length > 0 ||
    TAG_FACETS.some((d) => f[d].length > 0)
  );
}

const CONFIDENCE_RANK: Record<string, number> = { low: 0, medium: 1, high: 2 };

export type SortKey = 'confidence' | 'card' | 'id' | 'surface';

/** Sort a copy of the signals. Confidence sorts weakest-first by default (the
 *  audit's whole point is surfacing what you can't trust). */
export function sortSignals(signals: Signal[], key: SortKey, asc: boolean): Signal[] {
  const dir = asc ? 1 : -1;
  const cmp = (a: Signal, b: Signal): number => {
    switch (key) {
      case 'confidence': {
        const d = (CONFIDENCE_RANK[a.tags.confidence] ?? 0) - (CONFIDENCE_RANK[b.tags.confidence] ?? 0);
        return d !== 0 ? d : a.id.localeCompare(b.id);
      }
      case 'card':
        return a.card.localeCompare(b.card) || a.id.localeCompare(b.id);
      case 'surface':
        return a.surface.localeCompare(b.surface) || a.id.localeCompare(b.id);
      default:
        return a.id.localeCompare(b.id);
    }
  };
  return [...signals].sort((a, b) => cmp(a, b) * dir);
}

// ── Filter ⇄ URL-query codec (shareable deep links) ───────────────────────────
// `#/signals?conf=low,medium&state=12&q=owner` — only non-empty facets ride the
// query, so a plain unfiltered view stays a clean `#/signals`.
/** The array-valued (multi-select) facet keys — everything except `text`. */
export type FacetKey = Exclude<keyof SignalFilters, 'text'>;

const QUERY_KEYS: Array<[string, FacetKey]> = [
  ['conf', 'confidence'],
  ['state', 'state'],
  ['card', 'card'],
  ['prio', 'priority'],
  ['origin', 'upstream_origin'],
  ['fresh', 'freshness_risk'],
  ['deriv', 'derivation_risk'],
  ['verif', 'verifiability'],
];

export function filtersToQuery(f: SignalFilters): string {
  const params = new URLSearchParams();
  if (f.text.trim()) params.set('q', f.text.trim());
  for (const [param, key] of QUERY_KEYS) {
    if (f[key].length) params.set(param, f[key].join(','));
  }
  return params.toString();
}

export function filtersFromQuery(query: string): SignalFilters {
  const f = emptyFilters();
  const params = new URLSearchParams(query);
  f.text = params.get('q') ?? '';
  for (const [param, key] of QUERY_KEYS) {
    const raw = params.get(param);
    if (raw) f[key] = raw.split(',').filter(Boolean);
  }
  return f;
}
