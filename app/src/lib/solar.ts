// National solar layer (UI overhaul #119). Mirrors the structures-first tower
// loader (towers.ts): each anchor state's solar facilities are read slim and
// unioned client-side into ONE persistent `solar-all` collection that survives
// state switches and section changes. Solar is context, not a filter target —
// it carries only an owner-name string (no owner-cluster id), so it cannot be
// cluster-filtered; the Structure-type filter toggles its visibility instead.

import type { Feature, FeatureCollection, Point } from 'geojson';
import { compositeAssetUrl, loadGeoJson, probeResource } from './data';
import type { FilterModel } from './filter-model';
import type { CompositeIndex } from './catalog';

/** Per-state solar facilities GeoJSON (the national layer's source files). */
export function solarGeojsonUrl(fips: string): string {
  return compositeAssetUrl(fips, 'solar_facilities.geojson');
}

/** Flat, MapLibre-friendly properties baked onto each solar point. */
export interface SolarProps {
  name: string;
  operator: string;
  /** State FIPS the facility belongs to. */
  state: string;
  capacity_mw: number | null;
}

export type SolarFeature = Feature<Point, SolarProps>;

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}
function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

/** Union each state's raw solar GeoJSON into one national point collection.
 *  Point features only (solar renders as dots); the input `state` is stamped
 *  onto every feature so a click resolves which state it belongs to. Pure —
 *  unit-tested; the map feeds the result straight to the `solar-all` source. */
export function mergeSolarPoints(
  inputs: { state: string; collection: FeatureCollection }[],
): FeatureCollection<Point, SolarProps> {
  const features: SolarFeature[] = [];
  for (const { state, collection } of inputs) {
    for (const f of collection.features) {
      if (f.geometry?.type !== 'Point') continue;
      const [lon, lat] = f.geometry.coordinates;
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
      const p = (f.properties ?? {}) as Record<string, unknown>;
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [lon, lat] },
        properties: {
          name: str(p.name),
          operator: str(p.operator),
          state,
          capacity_mw: num(p.capacity_mw),
        },
      });
    }
  }
  return { type: 'FeatureCollection', features };
}

/**
 * Load solar points across every anchor state into one national collection.
 * Probes each `solar_facilities.geojson` first and unions only the present
 * ones, so a state missing the file degrades to "fewer solar dots" instead of
 * a failed boot. Mirrors `loadTowerPoints`.
 */
export async function loadSolarPoints(
  fipsList: string[],
): Promise<FeatureCollection<Point, SolarProps>> {
  const inputs = await Promise.all(
    fipsList.map(async (state): Promise<{ state: string; collection: FeatureCollection } | null> => {
      const url = solarGeojsonUrl(state);
      if ((await probeResource(url)) !== 'present') return null;
      const collection = await loadGeoJson(url).catch(() => null);
      return collection ? { state, collection } : null;
    }),
  );
  return mergeSolarPoints(inputs.filter((i): i is { state: string; collection: FeatureCollection } => i !== null));
}

/** Solar is shown on the map iff the Structure-type filter includes solar.
 *  The default model (no structure types) hides it, preserving today's
 *  "solar off by default". Pure predicate — the single control for solar
 *  visibility (the Layers panel is retired). */
export function showSolarLayer(model: FilterModel): boolean {
  return model.structureTypes.includes('solar');
}

/** Sum of each anchor state's solar-facility count — the static Solar tile.
 *  Solar cannot be cluster-filtered, so this total is fixed regardless of the
 *  active filter (it is "coverage across the anchor states", not a live match).
 *  Null index / missing counts contribute zero. Pure. */
export function solarTotal(index: CompositeIndex | null): number {
  if (!index) return 0;
  return index.states.reduce((n, s) => n + (s.counts.solar_facility ?? 0), 0);
}
