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

/** Layers shown by default when a state loads. (UI overhaul round 3: the
 *  map is now towers + solar + parcels only — distress is a filter field, not
 *  a coloured overlay, and the derived-view overlays were retired.) */
const DEFAULT_ON: ReadonlySet<string> = new Set(['towers']);

/** Catalog layers the redesigned app no longer surfaces on the map or in the
 *  LayerPanel. `distress_overlays` (OZ + QCT polygons) became a filter field
 *  in the top filter bar, so it's neither loaded nor drawn (UI overhaul
 *  round 3). Kept in the catalog/schema so its detail panel still resolves. */
export const HIDDEN_LAYERS: ReadonlySet<string> = new Set(['distress_overlays']);

export interface LoadableAsset {
  name: string;
  geojsonPath: string;
}

/** Catalog layers the structures-first map renders itself, not as per-state
 *  GeoJSON. `towers` is served across ALL anchors as one clustered DuckDB-fed
 *  layer (Slice 4 / #50), so the per-state ~20 MB towers.geojson is neither
 *  eager-loaded nor drawn here — the global tower layer owns it. */
export const MAP_OWNED_LAYERS: ReadonlySet<string> = new Set(['towers']);

/** Catalog GeoJSON layers small enough to boot-load. Views (the retired
 *  "derived outreach segments") and hidden / map-owned layers are skipped. */
export function eagerAssets(catalog: Catalog): LoadableAsset[] {
  const out: LoadableAsset[] = [];
  for (const l of catalog.layers) {
    if (
      l.geojsonPath &&
      !HEAVY_VIEWS.has(l.name) &&
      !MAP_OWNED_LAYERS.has(l.name) &&
      !HIDDEN_LAYERS.has(l.name)
    ) {
      out.push({ name: l.name, geojsonPath: l.geojsonPath });
    }
  }
  return out;
}

/** Initial visibility for every rendered GeoJSON layer of a catalog. Hidden
 *  layers and views (no longer drawn) are omitted. */
export function defaultVisibility(catalog: Catalog): Record<string, boolean> {
  const vis: Record<string, boolean> = {};
  for (const l of catalog.layers) {
    if (l.geojsonPath && !HIDDEN_LAYERS.has(l.name)) vis[l.name] = DEFAULT_ON.has(l.name);
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

/** Reflect the active state in the URL so a reload reopens it.
 *  Idempotent — the post-boot `$effect` in App.svelte also keeps the
 *  URL synced, so we no-op when the URL already matches. */
export function syncStateParam(fips: string): void {
  if (typeof history === 'undefined') return;
  const url = new URL(location.href);
  if (url.searchParams.get('state') === fips) return;
  url.searchParams.set('state', fips);
  history.replaceState(null, '', url);
}

/** Render an unknown thrown value as a user-displayable string. */
export function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** Union of state bboxes (`[w, s, e, n]`) into `fitBounds` corners
 *  `[[w, s], [e, n]]` — the all-anchors map framing. Null for no states. */
export function unionBounds(
  states: { bbox: [number, number, number, number] }[],
): [[number, number], [number, number]] | null {
  if (states.length === 0) return null;
  let w = Infinity;
  let s = Infinity;
  let e = -Infinity;
  let n = -Infinity;
  for (const st of states) {
    const [bw, bs, be, bn] = st.bbox;
    if (bw < w) w = bw;
    if (bs < s) s = bs;
    if (be > e) e = be;
    if (bn > n) n = bn;
  }
  return [
    [w, s],
    [e, n],
  ];
}
