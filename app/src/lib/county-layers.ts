/**
 * County-distress choropleth (audit fix M-d / #209). The preprocess pipeline
 * bakes a per-state `county_boundaries.geojson` (Census county polygons joined
 * with the ARC distress tier + USDA persistent-poverty flags) as the low-zoom
 * distress shading layer — but it was never wired into MapView. This module is
 * the pure half of that wiring: the loader that unions the per-state files into
 * one national collection (mirrors `solar.ts`), and the zoom/opacity appearance
 * that hands off to the parcel layer's own distress tint.
 *
 * Counties are *context*, not a filter target — the layer is display-only and
 * off by default (the map stays structures-first, #50); the FilterPanel's
 * Distress section carries its toggle.
 */

import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson';
import { countyBoundariesUrl, loadGeoJson, probeResource } from './data';
import { Z_ON } from './parcel-layers';

/** Layer-visibility key for the choropleth in `app.layerVisible` — absent from
 *  the boot defaults, so the layer starts off. */
export const COUNTIES_LAYER = 'counties';

/** Flat properties baked onto each county polygon. `tier` is the ARC distress
 *  tier ('' when the county has no ARC row — MT/FL counties mostly). */
export interface CountyProps {
  county_fips: string;
  county_name: string;
  /** State FIPS the county belongs to. */
  state: string;
  tier: string;
  persistent_poverty: boolean;
}

export type CountyFeature = Feature<Polygon | MultiPolygon, CountyProps>;

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

/** Union each state's county_boundaries.geojson into one national polygon
 *  collection. Polygonal features only; the input `state` is stamped onto
 *  every feature. Pure — unit-tested; the map feeds the result straight to
 *  the `counties-all` source. */
export function mergeCountyBoundaries(
  inputs: { state: string; collection: FeatureCollection }[],
): FeatureCollection<Polygon | MultiPolygon, CountyProps> {
  const features: CountyFeature[] = [];
  for (const { state, collection } of inputs) {
    for (const f of collection.features) {
      if (f.geometry?.type !== 'Polygon' && f.geometry?.type !== 'MultiPolygon') continue;
      const p = (f.properties ?? {}) as Record<string, unknown>;
      features.push({
        type: 'Feature',
        geometry: f.geometry,
        properties: {
          county_fips: str(p.county_fips),
          county_name: str(p.county_name),
          state,
          tier: str(p.tier),
          persistent_poverty: p.persistent_poverty === true,
        },
      });
    }
  }
  return { type: 'FeatureCollection', features };
}

/**
 * Load county boundaries across every anchor state into one national
 * collection. Probes each `county_boundaries.geojson` first and unions only
 * the present ones, so a state missing the file degrades to "fewer shaded
 * counties" instead of a failed toggle. Mirrors `loadSolarPoints`.
 */
export async function loadCountyBoundaries(
  fipsList: string[],
): Promise<FeatureCollection<Polygon | MultiPolygon, CountyProps>> {
  const inputs = await Promise.all(
    fipsList.map(async (state): Promise<{ state: string; collection: FeatureCollection } | null> => {
      const url = countyBoundariesUrl(state);
      if ((await probeResource(url)) !== 'present') return null;
      const collection = await loadGeoJson(url).catch(() => null);
      return collection ? { state, collection } : null;
    }),
  );
  return mergeCountyBoundaries(
    inputs.filter((i): i is { state: string; collection: FeatureCollection } => i !== null),
  );
}

/** County layer zoom + opacity. Counties shade the map at low zoom and hand
 *  off as parcels — which carry their own per-parcel distress tint — finish
 *  their pop-in ramp (`Z_ON → Z_ON + 0.5`, see parcel-layers.ts). */
export interface CountyLayerAppearance {
  /** Layer `maxzoom`: counties are not rendered once parcels are fully on. */
  maxzoom: number;
  fillOpacity: number;
  lineOpacity: number;
}

export function countyLayerAppearance(zOn: number = Z_ON): CountyLayerAppearance {
  return { maxzoom: zOn + 0.5, fillOpacity: 0.32, lineOpacity: 0.5 };
}
