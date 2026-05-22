/**
 * URL ↔ app-state sync. The query string carries the active state, the
 * selected parcel, and any active filters, so a URL is a shareable deep
 * link that restores the same view on reload.
 *
 * `?state=05&selected=<parcel_id>&filters=<json>` — `filters` holds only
 * the non-default fields, JSON-encoded, so a plain unfiltered view stays
 * a clean URL.
 */

import { emptyFilters, type FilterState } from './filters';

export interface UrlState {
  state: string | null;
  selected: string | null;
  /** null when the URL carries no filters param. */
  filters: FilterState | null;
}

/** The filter fields that differ from the unconstrained defaults. */
function activeFilterFields(f: FilterState): Partial<FilterState> {
  const defaults = emptyFilters();
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(defaults) as (keyof FilterState)[]) {
    if (JSON.stringify(f[key]) !== JSON.stringify(defaults[key])) {
      out[key] = f[key];
    }
  }
  return out as Partial<FilterState>;
}

export function encodeFilters(f: FilterState): string {
  return JSON.stringify(activeFilterFields(f));
}

/** Merge a URL `filters` param onto the defaults — tolerant of junk. */
export function decodeFilters(raw: string): FilterState {
  const result = emptyFilters();
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const obj = parsed as Record<string, unknown>;
      const target = result as unknown as Record<string, unknown>;
      for (const key of Object.keys(result)) {
        if (key in obj) {
          // The store only ever reads known keys; composeWhere escapes /
          // validates, so a hand-crafted URL cannot inject SQL.
          target[key] = obj[key];
        }
      }
    }
  } catch {
    // malformed filters param — fall back to no filters
  }
  return result;
}

export function readUrlState(search: string): UrlState {
  const params = new URLSearchParams(search);
  const filters = params.get('filters');
  return {
    state: params.get('state'),
    selected: params.get('selected'),
    filters: filters ? decodeFilters(filters) : null,
  };
}

/** The query string (`?…`, or a bare path) for the current app state. */
export function buildUrl(
  pathname: string,
  state: string | null,
  selected: string | null,
  filters: FilterState,
): string {
  const params = new URLSearchParams();
  if (state) params.set('state', state);
  if (selected) params.set('selected', selected);
  const active = activeFilterFields(filters);
  if (Object.keys(active).length > 0) params.set('filters', JSON.stringify(active));
  const qs = params.toString();
  return qs ? `${pathname}?${qs}` : pathname;
}
