// Last-map-position cache (PRD #121). The "where I left off" view is a local,
// per-device thing (it changes on every pan/zoom), so it lives in localStorage
// rather than the backend per-user store — unlike the pinned "home" view, which
// follows the user across devices via UserSettings. MapView writes it on
// `moveend`; the map-boot resolver and Settings ("Set current view as home")
// read it.

import { parseMapView, type MapView } from './basemap';

const LAST_VIEW_KEY = 'map.lastView';

export function readLastView(): MapView | null {
  try {
    return parseMapView(localStorage.getItem(LAST_VIEW_KEY) ?? '');
  } catch {
    return null;
  }
}

export function writeLastView(v: MapView): void {
  try {
    localStorage.setItem(LAST_VIEW_KEY, JSON.stringify(v));
  } catch {
    // storage disabled — last position just won't persist across reloads
  }
}
