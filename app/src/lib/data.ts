/**
 * Data fetching.
 *
 * Every path is root-relative (`/data/...`). In dev, Vite proxies `/data`
 * to the repo-root static server (see vite.config.ts); in a demo both
 * are served from one origin. The app never hardcodes a host.
 *
 * Fetch failures produce actionable Error messages — the boot flow turns
 * them into an on-screen message instead of a blank screen.
 */

import type { FeatureCollection } from 'geojson';
import { parseCompositeIndex, type CompositeIndex } from './catalog';

const COMPOSITE_ROOT = '/data/processed/composite';

export function indexUrl(): string {
  return `${COMPOSITE_ROOT}/index.json`;
}
/** The precomputed combined tower file — one national `towers.json` the map
 *  fetches directly instead of booting DuckDB-WASM on the tower path (#166). */
export function nationalTowersUrl(): string {
  return `${COMPOSITE_ROOT}/towers.json`;
}
/** URL of a file inside a state's composite directory (e.g. towers.geojson). */
export function compositeAssetUrl(fips: string, relPath: string): string {
  return `${COMPOSITE_ROOT}/${fips}/${relPath}`;
}

/** Per-state parcel vector tiles — discovered by convention (rehaul choice 3). */
export function pmtilesUrl(fips: string): string {
  return compositeAssetUrl(fips, 'parcels.pmtiles');
}

/** Per-state county-choropleth source. */
export function countyBoundariesUrl(fips: string): string {
  return compositeAssetUrl(fips, 'county_boundaries.geojson');
}

/** Outcome of a cheap HEAD probe. `unreachable` (the server is down /
 *  CORS / DNS) is kept distinct from `absent` (a real 404) so the caller
 *  can degrade silently on a genuine 404 but warn when the server is down
 *  rather than pretending the resource simply doesn't exist. */
export type ResourceProbe = 'present' | 'absent' | 'unreachable';

/**
 * Probe a resource via a cheap HEAD request. Used to discover
 * `parcels.pmtiles` / the slim parquet by convention — present → use it,
 * absent → degrade (choropleth only / filters off).
 */
export async function probeResource(url: string): Promise<ResourceProbe> {
  try {
    const res = await fetch(url, { method: 'HEAD' });
    return res.ok ? 'present' : 'absent';
  } catch {
    return 'unreachable';
  }
}

export async function fetchJson(url: string): Promise<unknown> {
  let res: Response;
  try {
    res = await fetch(url);
  } catch (e) {
    throw new Error(
      `Could not reach ${url}. Is the data server running ` +
        `(python scripts/serve.py 8765 at the repo root)? — ${String(e)}`,
    );
  }
  if (!res.ok) {
    throw new Error(`${url} — HTTP ${res.status} ${res.statusText}`);
  }
  try {
    return await res.json();
  } catch {
    throw new Error(`${url} — response was not valid JSON`);
  }
}

export async function loadIndex(): Promise<CompositeIndex> {
  return parseCompositeIndex(await fetchJson(indexUrl()));
}

export async function loadGeoJson(url: string): Promise<FeatureCollection> {
  const json = await fetchJson(url);
  if (
    !json ||
    typeof json !== 'object' ||
    (json as { type?: unknown }).type !== 'FeatureCollection' ||
    !Array.isArray((json as { features?: unknown }).features)
  ) {
    throw new Error(`${url} — not a GeoJSON FeatureCollection`);
  }
  return json as FeatureCollection;
}
