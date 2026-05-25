/**
 * Catalog contract round-trip: TS side.
 *
 * Reads the shared golden fixture from the repo root and asserts that
 * `parseCatalog` consumes every field correctly. The Python side
 * (tests/test_catalog_schema.py) validates the same fixture against
 * the JSON Schema. Together they enforce the Python ↔ TS contract:
 * if either side drifts from the shape under test, one of the suites
 * goes red.
 *
 * Targeted mutations also assert that the parser fails loudly when
 * required fields are missing — a regression to the previous silent-
 * coercion behaviour would slip through otherwise.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseCatalog, type Catalog } from '../../src/lib/catalog';

const GOLDEN_PATH = resolve(__dirname, '../../..', 'tests/fixtures/catalog/golden_catalog.json');

function loadGolden(): unknown {
  return JSON.parse(readFileSync(GOLDEN_PATH, 'utf8'));
}

describe('parseCatalog on the shared golden fixture', () => {
  it('round-trips every field from the shared golden_catalog.json', () => {
    const catalog: Catalog = parseCatalog(loadGolden());

    expect(catalog.schemaVersion).toBe(3);
    expect(catalog.stateFips).toBe('05');
    expect(catalog.stateName).toBe('Arkansas');
    expect(catalog.stateAbbr).toBe('AR');
    expect(catalog.generatedAt).toBe('2026-05-18T22:25:00Z');

    // Three layers — one of each interesting shape.
    expect(catalog.layers.map((l) => l.name).sort()).toEqual([
      'county_scores',
      'parcels',
      'towers',
    ]);

    const towers = catalog.layers.find((l) => l.name === 'towers')!;
    expect(towers.canonicalType).toBe('tower');
    expect(towers.rows).toBe(1873);
    expect(towers.geojsonPath).toBe('towers.geojson');
    expect(towers.simplifiedGeojsonPath).toBeUndefined();
    expect(towers.geometryType).toBe('Point');

    const parcels = catalog.layers.find((l) => l.name === 'parcels')!;
    expect(parcels.simplifiedGeojsonPath).toBe('parcels.simplified.geojson');
    expect(parcels.geojsonPath).toBeUndefined();

    const scores = catalog.layers.find((l) => l.name === 'county_scores')!;
    expect(scores.geometryType).toBeUndefined();
    expect(scores.geojsonPath).toBeUndefined();
    expect(scores.schema.state_fips).toBe('object');

    // Spatial view + tabular view.
    const llcView = catalog.views.find((v) => v.name === 'llc_owned_parcels_with_infra')!;
    expect(llcView.geometryType).toBe('Polygon');
    expect(llcView.inputs).toEqual(['parcel']);

    const ownerClusters = catalog.views.find((v) => v.name === 'owner_clusters')!;
    expect(ownerClusters.geometryType).toBeNull();
    expect(ownerClusters.geojsonPath).toBeUndefined();

    expect(catalog.sourcesUsedVersions).toEqual({
      ar_parcels: 'manual',
      fcc_asr: '2026-05-18',
      faa_oeaaa: '2026-05-15',
    });
  });
});

describe('parseCatalog fails loudly on contract violations', () => {
  it('throws when state_fips is missing', () => {
    const bad = loadGolden() as Record<string, unknown>;
    delete bad.state_fips;
    expect(() => parseCatalog(bad)).toThrow(/state_fips/);
  });

  it('throws when a required layer field is missing', () => {
    const bad = loadGolden() as Record<string, unknown>;
    const layers = bad.layers as Record<string, Record<string, unknown>>;
    delete layers.towers.canonical_type;
    expect(() => parseCatalog(bad)).toThrow(/layers\.towers\.canonical_type/);
  });

  it('throws when a required view field is missing', () => {
    const bad = loadGolden() as Record<string, unknown>;
    const views = bad.views as Record<string, Record<string, unknown>>;
    delete views.owner_clusters.description;
    expect(() => parseCatalog(bad)).toThrow(/views\.owner_clusters\.description/);
  });

  it('throws when schema_version is non-integer', () => {
    const bad = loadGolden() as Record<string, unknown>;
    bad.schema_version = '3';
    expect(() => parseCatalog(bad)).toThrow(/schema_version/);
  });

  it('throws when sources_used_versions is missing', () => {
    const bad = loadGolden() as Record<string, unknown>;
    delete bad.sources_used_versions;
    expect(() => parseCatalog(bad)).toThrow(/sources_used_versions/);
  });

  it('throws when view geometry_type is wrong type', () => {
    const bad = loadGolden() as Record<string, unknown>;
    const views = bad.views as Record<string, Record<string, unknown>>;
    views.owner_clusters.geometry_type = 42;
    expect(() => parseCatalog(bad)).toThrow(/geometry_type/);
  });

  it('throws when layers is not an object', () => {
    const bad = loadGolden() as Record<string, unknown>;
    bad.layers = [];
    expect(() => parseCatalog(bad)).toThrow(/layers/);
  });
});
