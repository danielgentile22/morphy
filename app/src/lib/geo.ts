/**
 * Geometry helpers — bounding boxes for fit-to / fly-to.
 *
 * All coordinates are lon/lat (EPSG:4326) — every preprocess output is
 * reprojected to WGS84.
 */

import type { Geometry, Position } from 'geojson';

/** [minX, minY, maxX, maxY] (lon/lat). */
export type BBox = [number, number, number, number];

function extendFromPosition(p: Position, b: BBox): void {
  const x = p[0];
  const y = p[1];
  if (typeof x !== 'number' || typeof y !== 'number') return;
  if (x < b[0]) b[0] = x;
  if (y < b[1]) b[1] = y;
  if (x > b[2]) b[2] = x;
  if (y > b[3]) b[3] = y;
}

function extendFromCoords(coords: unknown, b: BBox): void {
  if (!Array.isArray(coords)) return;
  if (typeof coords[0] === 'number') {
    extendFromPosition(coords as Position, b);
    return;
  }
  for (const c of coords) extendFromCoords(c, b);
}

/** Bounding box of any GeoJSON geometry, or null if it has no coordinates. */
export function geometryBounds(geom: Geometry | null | undefined): BBox | null {
  if (!geom) return null;
  const b: BBox = [Infinity, Infinity, -Infinity, -Infinity];
  if (geom.type === 'GeometryCollection') {
    for (const g of geom.geometries) mergeBBox(b, geometryBounds(g));
  } else {
    extendFromCoords(geom.coordinates, b);
  }
  return isValidBBox(b) ? b : null;
}

/** True when a bbox is four finite numbers with min ≤ max on both axes. */
export function isValidBBox(b: unknown): b is BBox {
  return (
    Array.isArray(b) &&
    b.length === 4 &&
    b.every((n) => typeof n === 'number' && Number.isFinite(n)) &&
    b[0] <= b[2] &&
    b[1] <= b[3]
  );
}

/** Grow `target` in place to also cover `other` (a no-op if `other` is null). */
export function mergeBBox(target: BBox, other: BBox | null): void {
  if (!other) return;
  if (other[0] < target[0]) target[0] = other[0];
  if (other[1] < target[1]) target[1] = other[1];
  if (other[2] > target[2]) target[2] = other[2];
  if (other[3] > target[3]) target[3] = other[3];
}

/** Centre [lon, lat] of a bbox. */
export function bboxCenter(b: BBox): [number, number] {
  return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
}

/** Parse a `geom_bbox` cell ('[w,s,e,n]' JSON string) into a BBox, or null. */
export function parseGeomBbox(raw: unknown): BBox | null {
  if (typeof raw !== 'string') return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return isValidBBox(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/** Which geometry families a feature collection contains. */
export interface GeometryClasses {
  hasPolygon: boolean;
  hasPoint: boolean;
  hasLine: boolean;
}

/**
 * Detect the geometry families present in a feature collection. Layers
 * are not always single-geometry — `solar_facilities` mixes Point,
 * Polygon and MultiPolygon — so the map decides which MapLibre sublayers
 * to add from this, not from `catalog.geometry_type`.
 */
export function detectGeometryClasses(
  features: ReadonlyArray<{ geometry: Geometry | null }>,
): GeometryClasses {
  const c: GeometryClasses = { hasPolygon: false, hasPoint: false, hasLine: false };
  for (const f of features) {
    const t = f.geometry?.type;
    if (t === 'Polygon' || t === 'MultiPolygon') c.hasPolygon = true;
    else if (t === 'Point' || t === 'MultiPoint') c.hasPoint = true;
    else if (t === 'LineString' || t === 'MultiLineString') c.hasLine = true;
    if (c.hasPolygon && c.hasPoint && c.hasLine) break;
  }
  return c;
}
