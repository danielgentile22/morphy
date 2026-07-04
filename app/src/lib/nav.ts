/**
 * Top-level navigation model (UI overhaul P1 / #104, ADR-065).
 *
 * The app is three sections — **Dashboard · Explore · Leads**. The Dashboard
 * renders all its digests on one page (PRD #125). Routing is hash-based so the
 * persistent MapLibre map (in Explore) never unmounts on navigation; the map's
 * own deep-link state (active state, selected parcel, filters) rides the query
 * string separately (see url.ts).
 *
 * Pure + unit-tested: parse a hash → a Route; map a Route → its nav Section
 * and back to a hash. App.svelte is the only consumer.
 */

/** The three top-level nav sections. */
export type Section = 'dashboard' | 'explore' | 'leads';

export type Route =
  | { name: 'dashboard' }
  | { name: 'explore' }
  | { name: 'leads' }
  /** An owner page (the Lead page) — reached from a Leads card or an Explore
   *  tower's owner link. Nav-wise it belongs to the Leads section. */
  | { name: 'lead'; key: string }
  /** A tower detail page (#108) — reached from the Explore map or list.
   *  ``cid`` is the owner's display_cluster_id (to load the owner), or the
   *  ``NO_OWNER`` sentinel for a tower with no resolved landowner (an unowned
   *  tower still gets a page — UI overhaul round 2). ``asr`` is the tower.
   *  Nav-wise it belongs to Explore. */
  | { name: 'tower'; cid: string; asr: string }
  /** The per-user Settings page (PRD #121) — reached from the user-menu
   *  dropdown, not a primary nav tab. One flat route; its four sections
   *  (Account / Map & display / Filter defaults / Automations) are local
   *  component state, not sub-routes. */
  | { name: 'settings' };

/** Sentinel `cid` segment for an unowned tower's URL — keeps `#/tower/<cid>/<asr>`
 *  well-formed when there's no owner cluster to address (the segment can't be
 *  empty or the route fails to parse). */
export const NO_OWNER = '-';

/** Parse a `location.hash` into a Route. Empty/unknown → the Dashboard, so
 *  the app opens on the Dashboard (user story 1). */
export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  if (parts[0] === 'lead' && parts[1]) return { name: 'lead', key: decodeURIComponent(parts[1]) };
  if (parts[0] === 'tower' && parts[1] && parts[2]) {
    return { name: 'tower', cid: decodeURIComponent(parts[1]), asr: decodeURIComponent(parts[2]) };
  }
  if (parts[0] === 'explore') return { name: 'explore' };
  if (parts[0] === 'leads') return { name: 'leads' };
  if (parts[0] === 'settings') return { name: 'settings' };
  return { name: 'dashboard' };
}

/** Which top-level nav tab is active for a route. A lead/owner page lights
 *  the Leads tab (the owner is the unit of work). */
export function sectionOf(route: Route): Section {
  switch (route.name) {
    case 'explore':
    case 'tower':
      return 'explore';
    case 'leads':
    case 'lead':
      return 'leads';
    default:
      return 'dashboard';
  }
}

/** The canonical hash for a top-level section. */
export const SECTION_HASH: Record<Section, string> = {
  dashboard: '#/dashboard',
  explore: '#/explore',
  leads: '#/leads',
};

/** The hash for an owner (Lead) page. */
export function leadHash(displayClusterId: string): string {
  return `#/lead/${encodeURIComponent(displayClusterId)}`;
}

/** The canonical hash for the Settings page (PRD #121). */
export function settingsHash(): string {
  return '#/settings';
}

/** The hash for a tower detail page (#108). An empty `cid` (an unowned tower)
 *  is substituted with the `NO_OWNER` sentinel so the URL stays well-formed —
 *  the tower still gets an openable page. */
export function towerHash(cid: string, asr: string): string {
  return `#/tower/${encodeURIComponent(cid || NO_OWNER)}/${encodeURIComponent(asr)}`;
}

/** True when a tower route's `cid` addresses no owner (the unowned-tower case). */
export function isUnowned(cid: string): boolean {
  return cid === '' || cid === NO_OWNER;
}
