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
import {
  parseCatalog,
  parseCompositeIndex,
  type Catalog,
  type CompositeIndex,
} from './catalog';
import { parseFacets, type FacetData } from './facets';

const COMPOSITE_ROOT = '/data/processed/composite';

export function indexUrl(): string {
  return `${COMPOSITE_ROOT}/index.json`;
}
export function catalogUrl(fips: string): string {
  return `${COMPOSITE_ROOT}/${fips}/catalog.json`;
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

/** Per-state slim attribute parquet — the DuckDB-WASM filter engine's input. */
export function parcelsAttrUrl(fips: string): string {
  return compositeAssetUrl(fips, 'parcels_attr.parquet');
}

/** Per-state precomputed filter facets. */
export function facetsUrl(fips: string): string {
  return compositeAssetUrl(fips, 'facets.json');
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

async function fetchJson(url: string): Promise<unknown> {
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

export async function loadCatalog(fips: string): Promise<Catalog> {
  return parseCatalog(await fetchJson(catalogUrl(fips)));
}

export async function loadFacets(fips: string): Promise<FacetData> {
  return parseFacets(await fetchJson(facetsUrl(fips)));
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
