import { describe, it, expect } from 'vitest';
import type { Geometry } from 'geojson';
import {
  geometryBounds,
  isValidBBox,
  mergeBBox,
  bboxCenter,
  parseGeomBbox,
  detectGeometryClasses,
  type BBox,
} from '../../src/lib/geo';

describe('geometryBounds', () => {
  it('bounds a Point', () => {
    const g: Geometry = { type: 'Point', coordinates: [-91.3, 33.0] };
    expect(geometryBounds(g)).toEqual([-91.3, 33.0, -91.3, 33.0]);
  });

  it('bounds a Polygon', () => {
    const g: Geometry = {
      type: 'Polygon',
      coordinates: [
        [
          [-94, 33],
          [-90, 33],
          [-90, 36],
          [-94, 36],
          [-94, 33],
        ],
      ],
    };
    expect(geometryBounds(g)).toEqual([-94, 33, -90, 36]);
  });

  it('bounds a MultiPolygon', () => {
    const g: Geometry = {
      type: 'MultiPolygon',
      coordinates: [
        [
          [
            [-94, 33],
            [-93, 33],
            [-93, 34],
            [-94, 33],
          ],
        ],
        [
          [
            [-91, 35],
            [-90, 35],
            [-90, 36],
            [-91, 35],
          ],
        ],
      ],
    };
    expect(geometryBounds(g)).toEqual([-94, 33, -90, 36]);
  });

  it('bounds a GeometryCollection', () => {
    const g: Geometry = {
      type: 'GeometryCollection',
      geometries: [
        { type: 'Point', coordinates: [-94, 33] },
        { type: 'Point', coordinates: [-90, 36] },
      ],
    };
    expect(geometryBounds(g)).toEqual([-94, 33, -90, 36]);
  });

  it('returns null for null / empty geometry', () => {
    expect(geometryBounds(null)).toBeNull();
    expect(geometryBounds(undefined)).toBeNull();
    expect(geometryBounds({ type: 'Polygon', coordinates: [] })).toBeNull();
  });
});

describe('isValidBBox', () => {
  it('accepts a well-formed bbox', () => {
    expect(isValidBBox([-94.62, 33.0, -89.64, 36.5])).toBe(true);
  });
  it('rejects malformed bboxes', () => {
    expect(isValidBBox([-94, 33, -90])).toBe(false); // wrong length
    expect(isValidBBox([-94, 33, NaN, 36])).toBe(false); // non-finite
    expect(isValidBBox([-90, 33, -94, 36])).toBe(false); // minX > maxX
    expect(isValidBBox('nope')).toBe(false);
    expect(isValidBBox(null)).toBe(false);
  });
});

describe('mergeBBox', () => {
  it('grows a bbox to cover another', () => {
    const b: BBox = [-94, 33, -90, 36];
    mergeBBox(b, [-95, 32, -89, 37]);
    expect(b).toEqual([-95, 32, -89, 37]);
  });
  it('is a no-op for null', () => {
    const b: BBox = [-94, 33, -90, 36];
    mergeBBox(b, null);
    expect(b).toEqual([-94, 33, -90, 36]);
  });
});

describe('bboxCenter', () => {
  it('returns the centre point', () => {
    expect(bboxCenter([-94, 32, -90, 36])).toEqual([-92, 34]);
  });
});

describe('parseGeomBbox', () => {
  it('parses a geom_bbox JSON string', () => {
    expect(parseGeomBbox('[-90.43, 35.04, -90.41, 35.05]')).toEqual([-90.43, 35.04, -90.41, 35.05]);
  });
  it('rejects non-strings, malformed JSON, and wrong-shape arrays', () => {
    expect(parseGeomBbox(null)).toBeNull();
    expect(parseGeomBbox(42)).toBeNull();
    expect(parseGeomBbox('not json')).toBeNull();
    expect(parseGeomBbox('[1, 2, 3]')).toBeNull();
  });
});

describe('detectGeometryClasses', () => {
  it('detects a pure point layer (towers)', () => {
    const c = detectGeometryClasses([{ geometry: { type: 'Point', coordinates: [0, 0] } }]);
    expect(c).toEqual({ hasPolygon: false, hasPoint: true, hasLine: false });
  });

  it('detects a pure polygon layer (distress overlays)', () => {
    const c = detectGeometryClasses([
      { geometry: { type: 'Polygon', coordinates: [] } },
      { geometry: { type: 'MultiPolygon', coordinates: [] } },
    ]);
    expect(c).toEqual({ hasPolygon: true, hasPoint: false, hasLine: false });
  });

  it('detects mixed geometry (solar_facilities — Point + Polygon + MultiPolygon)', () => {
    const c = detectGeometryClasses([
      { geometry: { type: 'Point', coordinates: [0, 0] } },
      { geometry: { type: 'Polygon', coordinates: [] } },
      { geometry: { type: 'MultiPolygon', coordinates: [] } },
    ]);
    expect(c.hasPoint).toBe(true);
    expect(c.hasPolygon).toBe(true);
  });

  it('handles an empty / null-geometry collection', () => {
    expect(detectGeometryClasses([])).toEqual({
      hasPolygon: false,
      hasPoint: false,
      hasLine: false,
    });
    expect(detectGeometryClasses([{ geometry: null }])).toEqual({
      hasPolygon: false,
      hasPoint: false,
      hasLine: false,
    });
  });
});
