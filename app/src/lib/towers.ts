// Structures-first map: tower points across all anchor states (Slice 4 / #50).
//
// Towers are the primary, clustered map layer. They are sourced from the
// existing static read-layer — each state's `towers.parquet` — read slim and
// unioned client-side (DuckDB-WASM over HTTP Range), NOT from the ~99 MB of
// raw towers GeoJSON. A clicked tower resolves to its landowner's Lead via the
// owner-cluster key (see owner-cluster.ts), so no extra fetch is needed.
//
// Out of scope for this slice (other slices hook in here later): top-bar
// filters / owner+ASR search (#52) narrow this same tower set via shared
// filter state — `loadTowerPoints` is the single query seam they extend.

import type { Feature, FeatureCollection, Point } from 'geojson';
import { duckDb, type TowerRow, type TowerSource } from './duckdb';
import { compositeAssetUrl, probeResource } from './data';
import { ownerNameToClusterId } from './owner-cluster';

/** Per-state `towers.parquet` (the structures-first map's tower source). */
export function towersParquetUrl(fips: string): string {
  return compositeAssetUrl(fips, 'towers.parquet');
}

/** Flat, MapLibre-friendly properties baked onto each tower point. */
export interface TowerProps {
  asr: string;
  /** Landowner name (the parcel's owner) — drives hover + Lead resolution. */
  owner: string;
  height_m: number | null;
  state: string;
  active: boolean;
}

export type TowerFeature = Feature<Point, TowerProps>;

const M_PER_FT = 0.3048;

/** Tower height in whole feet (US convention; the map's scale bar is imperial). */
export function heightFeet(heightM: number | null | undefined): number | null {
  if (heightM == null || !Number.isFinite(heightM)) return null;
  return Math.round(heightM / M_PER_FT);
}

/** Landowner label for hover / resolution; blank parcel_owner → a clear stand-in. */
export function towerOwnerLabel(owner: string | null | undefined): string {
  const o = (owner ?? '').trim();
  return o || 'Unknown landowner';
}

/** Lead key for a clicked tower, or '' when its landowner is un-clusterable
 *  (blank name) — the caller treats '' as "no Lead to open". */
export function resolveTowerLeadKey(props: Pick<TowerProps, 'owner'>): string {
  return ownerNameToClusterId(props.owner);
}

/** Hover preview text: owner, ASR, height, state (acceptance criterion). */
export function towerHoverHtml(props: TowerProps): string {
  const ft = heightFeet(props.height_m);
  const bits = [`ASR ${escapeHtml(props.asr)}`];
  if (ft != null) bits.push(`${ft} ft`);
  bits.push(escapeHtml(props.state));
  return `<strong>${escapeHtml(towerOwnerLabel(props.owner))}</strong><br>${bits.join(' · ')}`;
}

function escapeHtml(s: string): string {
  return s.replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!,
  );
}

/** Turn slim DuckDB rows into a GeoJSON FeatureCollection of tower points.
 *  Rows without finite coordinates are dropped. Pure — unit-tested. */
export function rowsToFeatureCollection(rows: TowerRow[]): FeatureCollection<Point, TowerProps> {
  const features: TowerFeature[] = [];
  for (const r of rows) {
    if (!Number.isFinite(r.lon) || !Number.isFinite(r.lat)) continue;
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [r.lon, r.lat] },
      properties: {
        asr: String(r.asr ?? ''),
        owner: (r.owner ?? '').trim(),
        height_m: r.height_m ?? null,
        state: String(r.state ?? ''),
        active: r.active === true,
      },
    });
  }
  return { type: 'FeatureCollection', features };
}

/**
 * Load tower points for the given anchor states into one FeatureCollection.
 * Probes each `towers.parquet` first and queries only the present ones, so a
 * state missing the file degrades to "fewer towers" instead of an empty map.
 */
export async function loadTowerPoints(
  fipsList: string[],
): Promise<FeatureCollection<Point, TowerProps>> {
  const probes = await Promise.all(
    fipsList.map(async (fips): Promise<TowerSource | null> => {
      const url = towersParquetUrl(fips);
      return (await probeResource(url)) === 'present' ? { fips, url } : null;
    }),
  );
  const sources = probes.filter((s): s is TowerSource => s !== null);
  const rows = await duckDb.loadTowerPoints(sources);
  return rowsToFeatureCollection(rows);
}
