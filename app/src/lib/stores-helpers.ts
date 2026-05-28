/**
 * Pure helpers for the AppStore boot flow.
 *
 * Lives outside `stores.svelte.ts` so each piece is unit-testable
 * without spinning up Svelte runes / DOM. The store itself stays thin —
 * it sequences these helpers and writes their results into `$state`
 * fields.
 */

import type { Catalog } from './catalog';
import type { StateEntry } from './catalog';

/** Views whose GeoJSON is large enough that we lazy-load on first toggle. */
export const HEAVY_VIEWS: ReadonlySet<string> = new Set([
  'parcels_hosting_infra',
  'distressed_parcels_hosting_infra',
  'llc_owned_parcels_with_infra',
  'towers_with_landowner',
]);

/** Layers / views shown by default when a state loads. */
const DEFAULT_ON: ReadonlySet<string> = new Set([
  'towers',
  'distress_overlays',
  'interestingness_top_1000',
]);

export interface LoadableAsset {
  name: string;
  geojsonPath: string;
}

/** Layers + views that carry GeoJSON and are small enough to boot-load. */
export function eagerAssets(catalog: Catalog): LoadableAsset[] {
  const out: LoadableAsset[] = [];
  for (const l of catalog.layers) {
    if (l.geojsonPath && !HEAVY_VIEWS.has(l.name)) {
      out.push({ name: l.name, geojsonPath: l.geojsonPath });
    }
  }
  for (const v of catalog.views) {
    if (v.geojsonPath && !HEAVY_VIEWS.has(v.name)) {
      out.push({ name: v.name, geojsonPath: v.geojsonPath });
    }
  }
  return out;
}

/** Initial visibility for every GeoJSON-bearing layer / view of a catalog. */
export function defaultVisibility(catalog: Catalog): Record<string, boolean> {
  const vis: Record<string, boolean> = {};
  for (const l of catalog.layers) {
    if (l.geojsonPath) vis[l.name] = DEFAULT_ON.has(l.name);
  }
  for (const v of catalog.views) {
    if (v.geojsonPath) vis[v.name] = DEFAULT_ON.has(v.name);
  }
  return vis;
}

/** Decide which state to open from the URL `?state=` param. */
export function pickInitialState(
  search: string,
  states: StateEntry[],
): { fips: string; invalidRequest: string | null } {
  const requested = new URLSearchParams(search).get('state');
  if (requested && states.some((s) => s.fips === requested)) {
    return { fips: requested, invalidRequest: null };
  }
  return {
    fips: states[0]?.fips ?? '',
    invalidRequest: requested && requested.trim() !== '' ? requested : null,
  };
}

/** Reflect the active state in the URL so a reload reopens it. */
export function syncStateParam(fips: string): void {
  if (typeof history === 'undefined') return;
  const url = new URL(location.href);
  url.searchParams.set('state', fips);
  history.replaceState(null, '', url);
}

/** Render an unknown thrown value as a user-displayable string. */
export function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
