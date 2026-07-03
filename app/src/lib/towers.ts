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
import { compositeAssetUrl, fetchJson, nationalTowersUrl, probeResource } from './data';
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
  /** Landowner's cross-state Lead key (`display_cluster_id`), precomputed once
   *  so the shared FilterModel can narrow towers by an owner-id set lookup
   *  (Slice 6 / #52) without re-hashing every owner name on each filter change.
   *  '' when the owner can't be clustered (blank name). */
  cid: string;
  height_m: number | null;
  state: string;
  active: boolean;
  /** Construction date (audit M-c / #208) — null when granted-but-not-built. */
  date_built: string | null;
  /** The ASR registrant — the towerco/carrier lease counterparty (audit M-b).
   *  NOT the landowner: `owner` above is the parcel's owner. Null on
   *  FAA-sourced rows; ~99% populated on FCC rows. */
  tower_owner: string | null;
  tower_owner_street: string | null;
  tower_owner_city: string | null;
  tower_owner_state: string | null;
  tower_owner_zip: string | null;
  tower_owner_phone: string | null;
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
  const text = (v: string | null | undefined): string | null => {
    const s = (v ?? '').trim();
    return s === '' ? null : s;
  };
  for (const r of rows) {
    if (!Number.isFinite(r.lon) || !Number.isFinite(r.lat)) continue;
    const owner = (r.owner ?? '').trim();
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [r.lon, r.lat] },
      properties: {
        asr: String(r.asr ?? ''),
        owner,
        // Prefer the builder-baked Lead key (#166); recompute only when it's
        // absent (per-state DuckDB path / a stale towers.json). Same recipe,
        // so the two agree — pinned by the owner-cluster parity test.
        cid: typeof r.cid === 'string' ? r.cid : ownerNameToClusterId(owner),
        height_m: r.height_m ?? null,
        state: String(r.state ?? ''),
        active: r.active === true,
        date_built: text(r.date_built),
        tower_owner: text(r.tower_owner),
        tower_owner_street: text(r.tower_owner_street),
        tower_owner_city: text(r.tower_owner_city),
        tower_owner_state: text(r.tower_owner_state),
        tower_owner_zip: text(r.tower_owner_zip),
        tower_owner_phone: text(r.tower_owner_phone),
      },
    });
  }
  return { type: 'FeatureCollection', features };
}

/** Per-antenna archive narrowing (UI overhaul round 2): archived ASRs drop out
 *  of the map + list unless the user opts into showing them. ASR-grained, so
 *  it's applied alongside the owner-cluster narrowing, not folded into it. */
export interface ArchivedFilter {
  asrs: ReadonlySet<string>;
  show: boolean;
}

/** Narrow a tower collection to owners in `clusterIds` (`null` = no owner
 *  filter), then drop archived towers unless `archived.show`. Returns the
 *  collection unchanged when nothing narrows it. Pure — unit-tested; the map
 *  feeds the result straight to the tower source's `setData`. */
export function filterTowers(
  fc: FeatureCollection<Point, TowerProps>,
  clusterIds: ReadonlySet<string> | null,
  archived?: ArchivedFilter,
): FeatureCollection<Point, TowerProps> {
  const hideArchived = archived !== undefined && !archived.show && archived.asrs.size > 0;
  if (clusterIds === null && !hideArchived) return fc;
  return {
    type: 'FeatureCollection',
    features: fc.features.filter(
      (f) =>
        (clusterIds === null || clusterIds.has(f.properties.cid)) &&
        !(hideArchived && archived.asrs.has(f.properties.asr)),
    ),
  };
}

/**
 * Load tower points for the given anchor states into one FeatureCollection.
 * Probes each `towers.parquet` first and queries only the present ones, so a
 * state missing the file degrades to "fewer towers" instead of an empty map.
 *
 * This is the DuckDB-WASM path — kept as the fallback for `loadNationalTowers`
 * (a deploy before the combined file is regenerated). Booting the engine here
 * is the ~1.0 s cost the precomputed `towers.json` removes (PRD #163).
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

/** Map the rows of a parsed `composite/towers.json` to slim `TowerRow`s.
 *  Tolerant of missing keys so a stale file (an older schema) still loads —
 *  `rowsToFeatureCollection` then applies the very defaults the per-state path
 *  uses. The builder bakes `cid` (the owner Lead key); it is passed through
 *  when present and recomputed when absent. Throws only when the envelope has
 *  no `towers[]` array, so the loader can fall back. Pure — unit-tested. */
export function parseNationalTowers(json: unknown): TowerRow[] {
  const towers = (json as { towers?: unknown } | null)?.towers;
  if (!Array.isArray(towers)) throw new Error('towers.json — missing towers[] array');
  const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);
  return towers.map((t): TowerRow => {
    const r = (t ?? {}) as Record<string, unknown>;
    return {
      asr: String(r.asr ?? ''),
      owner: str(r.owner),
      height_m: typeof r.height_m === 'number' ? r.height_m : null,
      state: String(r.state ?? ''),
      active: typeof r.active === 'boolean' ? r.active : null,
      lat: typeof r.lat === 'number' ? r.lat : Number.NaN,
      lon: typeof r.lon === 'number' ? r.lon : Number.NaN,
      ...(typeof r.cid === 'string' ? { cid: r.cid } : {}),
      // v2 fields (audit M-b/M-c) — absent on a stale v1 file → null defaults.
      date_built: str(r.date_built),
      tower_owner: str(r.tower_owner),
      tower_owner_street: str(r.tower_owner_street),
      tower_owner_city: str(r.tower_owner_city),
      tower_owner_state: str(r.tower_owner_state),
      tower_owner_zip: str(r.tower_owner_zip),
      tower_owner_phone: str(r.tower_owner_phone),
    };
  });
}

/**
 * Load the national tower layer from the precomputed `composite/towers.json`,
 * mapping its rows through the same pure `rowsToFeatureCollection` the
 * per-state path uses (so clustering, hover, filter joins and Lead resolution
 * are byte-for-byte unchanged).
 *
 * Probes the combined file first; if it is absent/unreachable (a deploy before
 * the data was regenerated) — or present but malformed — falls back to the
 * per-state DuckDB `loadTowerPoints` union. The map degrades to "towers via
 * DuckDB", never to "no towers". This is the tower-load seam: DuckDB-WASM is
 * not touched unless the fallback fires.
 */
export async function loadNationalTowers(
  fipsList: string[],
): Promise<FeatureCollection<Point, TowerProps>> {
  const url = nationalTowersUrl();
  if ((await probeResource(url)) === 'present') {
    try {
      return rowsToFeatureCollection(parseNationalTowers(await fetchJson(url)));
    } catch {
      // Present but unparseable → fall through to the per-state union.
    }
  }
  return loadTowerPoints(fipsList);
}
