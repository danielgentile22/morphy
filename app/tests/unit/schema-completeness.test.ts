/**
 * Schema-completeness — the regression guard for the failure mode that
 * broke the v1 app: detail panels full of "—" because the schema drifted
 * away from the composite's field names.
 *
 * Runs against the *real* AR + MT composite GeoJSON. Two checks per
 * entity kind:
 *   1. every field key the schema reads exists in the catalog's layer
 *      schema (catches a renamed / removed field at the source);
 *   2. every field produces a non-null value for at least one real
 *      feature whose keys carry data (catches a value fn reading the
 *      wrong key — drift between `keys` and `value`).
 */

/// <reference types="node" />
import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { ENTITY_SCHEMAS, type EntityKind } from '../../src/lib/schema';
import { parseCatalog } from '../../src/lib/catalog';
import { hasValue } from '../../src/lib/format';

// Vitest runs from app2/; the composite tree is one level up under data/.
const COMPOSITE = resolve(process.cwd(), '../data/processed/composite') + '/';

function readJson(rel: string): unknown {
  return JSON.parse(readFileSync(COMPOSITE + rel, 'utf-8'));
}

// Each entity kind: the catalog layer whose schema lists its fields (null
// for county — its source is an --app-assets GeoJSON, not a catalog
// layer), and the GeoJSON file to sample real features from.
const SOURCES: Record<EntityKind, { layer: string | null; geojson: string }> = {
  tower: { layer: 'towers', geojson: 'towers.geojson' },
  parcel: { layer: 'parcels', geojson: 'views/interestingness_top_1000.geojson' },
  solar: { layer: 'solar_facilities', geojson: 'solar_facilities.geojson' },
  distress_overlay: { layer: 'distress_overlays', geojson: 'distress_overlays.geojson' },
  county: { layer: null, geojson: 'county_boundaries.geojson' },
};

interface Feature {
  properties: Record<string, unknown>;
}

for (const fips of ['05', '30']) {
  const catalogPath = `${COMPOSITE}${fips}/catalog.json`;

  describe(`schema completeness — state ${fips}`, () => {
    if (!existsSync(catalogPath)) {
      it.skip(`composite/${fips} is not on disk`, () => {});
      return;
    }
    const catalog = parseCatalog(readJson(`${fips}/catalog.json`));

    for (const [kind, src] of Object.entries(SOURCES) as Array<
      [EntityKind, (typeof SOURCES)[EntityKind]]
    >) {
      const schema = ENTITY_SCHEMAS[kind];
      if (!schema) continue;
      const catalogLayer = catalog.layers.find((l) => l.name === src.layer);
      const fc = readJson(`${fips}/${src.geojson}`) as { features: Feature[] };
      // The whole file, not a head-slice: source-gated fields (e.g. the
      // FCC-only "ASR number" after the M-i split, #215) can be null across
      // any contiguous run of one source's rows — FAA rows lead the towers
      // layer. The render check below is a short-circuiting some(), so the
      // full scan stays cheap.
      const sample = fc.features;
      const fields = schema.sections.flatMap((s) => s.fields);

      if (src.layer) {
        it(`${kind}: every field key exists in the catalog '${src.layer}' schema`, () => {
          expect(catalogLayer, `catalog should declare a '${src.layer}' layer`).toBeDefined();
          const known = new Set(Object.keys(catalogLayer!.schema));
          for (const f of fields) {
            for (const key of f.keys) {
              expect(
                known.has(key),
                `${kind} field "${f.label}" reads "${key}" — absent from the catalog schema`,
              ).toBe(true);
            }
          }
        });
      }

      it(`${kind}: every field renders a value where the data is present`, () => {
        expect(sample.length, 'sample has features').toBeGreaterThan(0);
        for (const f of fields) {
          const populated = sample.filter((ft) =>
            f.keys.some((k) => hasValue(ft.properties?.[k])),
          );
          if (populated.length === 0) continue; // genuinely sparse — not drift
          const renders = populated.some((ft) => f.value(ft.properties) !== null);
          expect(
            renders,
            `${kind} field "${f.label}" is "—" for all ${populated.length} ` +
              `features that have ${f.keys.join('/')} — likely schema drift`,
          ).toBe(true);
        }
      });
    }

    it('parcel: the #1 interestingness parcel shows the pitch-critical fields', () => {
      const fc = readJson(`${fips}/views/interestingness_top_1000.geojson`) as {
        features: Feature[];
      };
      const top = fc.features[0].properties;
      const parcel = ENTITY_SCHEMAS.parcel!;
      const field = (label: string) =>
        parcel.sections.flatMap((s) => s.fields).find((f) => f.label === label)!;
      expect(field('Owner').value(top), 'landowner').not.toBeNull();
      expect(field('Market / appraised value').value(top), 'assessed value').not.toBeNull();
      expect(field('Score').value(top), 'interestingness score').not.toBeNull();
    });
  });
}
