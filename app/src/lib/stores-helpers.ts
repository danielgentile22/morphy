/**
 * Pure helpers for the AppStore boot flow.
 *
 * Lives outside `stores.svelte.ts` so each piece is unit-testable without
 * spinning up Svelte runes / DOM. The store itself stays thin — it sequences
 * these helpers and writes their results into `$state` fields.
 *
 * The per-state catalog/visibility selectors (eagerAssets / defaultVisibility /
 * pickInitialState) were retired with the state selector (UI overhaul #119):
 * the app loads all anchor states at once, so there is no "active state" to
 * pick or per-state catalog to eager-load.
 */

import { pmtilesUrl, type ResourceProbe } from './data';

/** One anchor state's parcel vector-tile source for the all-states map. */
export interface ParcelSource {
  /** State FIPS the source belongs to (drives multi-source click + highlight). */
  state: string;
  /** `pmtiles://`-ready URL of the state's parcels.pmtiles. */
  tilesUrl: string;
}

/** The parcel vector-tile sources the map should add — one per anchor state
 *  whose `parcels.pmtiles` HEAD-probed `present` (UI overhaul #119: parcels
 *  draw for every state, not just a selected one). A state that's absent or
 *  unreachable is dropped, so a missing tileset degrades to "fewer parcel
 *  sources" rather than a broken source. Input order is preserved. Pure. */
export function parcelSources(
  states: { fips: string }[],
  probes: Record<string, ResourceProbe>,
): ParcelSource[] {
  const out: ParcelSource[] = [];
  for (const { fips } of states) {
    if (probes[fips] === 'present') out.push({ state: fips, tilesUrl: pmtilesUrl(fips) });
  }
  return out;
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
