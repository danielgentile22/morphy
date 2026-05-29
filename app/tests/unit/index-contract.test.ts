/**
 * Composite-index contract round-trip: TS side.
 *
 * Reads the shared golden fixture from the repo root and asserts that
 * `parseCompositeIndex` consumes every field correctly. The Python
 * side (tests/test_index_schema.py) validates the same fixture against
 * the JSON Schema. Together they enforce the Python ↔ TS contract.
 *
 * Targeted mutations also assert that the parser fails loudly when
 * required fields are missing — a regression to the previous silent-
 * coercion behaviour would slip through otherwise.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseCompositeIndex, type CompositeIndex } from '../../src/lib/catalog';

const GOLDEN_PATH = resolve(__dirname, '../../..', 'tests/fixtures/catalog/golden_index.json');

function loadGolden(): unknown {
  return JSON.parse(readFileSync(GOLDEN_PATH, 'utf8'));
}

describe('parseCompositeIndex on the shared golden fixture', () => {
  it('round-trips every field from the shared golden_index.json', () => {
    const index: CompositeIndex = parseCompositeIndex(loadGolden());

    expect(index.schemaVersion).toBe(1);
    expect(index.generatedAt).toBe('2026-05-18T22:25:00Z');
    expect(index.states.map((s) => s.fips).sort()).toEqual(['05', '12', '30']);

    const ar = index.states.find((s) => s.fips === '05')!;
    expect(ar.abbr).toBe('AR');
    expect(ar.name).toBe('Arkansas');
    expect(ar.bbox).toEqual([-94.62, 33.0, -89.64, 36.5]);
    expect(ar.counts).toEqual({ parcel: 2116976, tower: 1873, county_score: 75 });

    const mt = index.states.find((s) => s.fips === '30')!;
    expect(mt.counts).toEqual({ parcel: 920111, tower: 642 });

    // A composed state can have zero rows in every layer; counts may be empty.
    const fl = index.states.find((s) => s.fips === '12')!;
    expect(fl.counts).toEqual({});
  });
});

describe('parseCompositeIndex fails loudly on contract violations', () => {
  it('throws when schema_version is missing', () => {
    const bad = loadGolden() as Record<string, unknown>;
    delete bad.schema_version;
    expect(() => parseCompositeIndex(bad)).toThrow(/schema_version/);
  });

  it('throws when generated_at is missing', () => {
    const bad = loadGolden() as Record<string, unknown>;
    delete bad.generated_at;
    expect(() => parseCompositeIndex(bad)).toThrow(/generated_at/);
  });

  it('throws when states is missing', () => {
    const bad = loadGolden() as Record<string, unknown>;
    delete bad.states;
    expect(() => parseCompositeIndex(bad)).toThrow(/states/);
  });

  it('throws when a state lacks fips', () => {
    const bad = loadGolden() as Record<string, unknown>;
    const states = bad.states as Record<string, unknown>[];
    delete states[0].fips;
    expect(() => parseCompositeIndex(bad)).toThrow(/fips/);
  });

  it('throws when a state lacks abbr', () => {
    const bad = loadGolden() as Record<string, unknown>;
    const states = bad.states as Record<string, unknown>[];
    delete states[0].abbr;
    expect(() => parseCompositeIndex(bad)).toThrow(/abbr/);
  });

  it('throws when a state lacks name', () => {
    const bad = loadGolden() as Record<string, unknown>;
    const states = bad.states as Record<string, unknown>[];
    delete states[0].name;
    expect(() => parseCompositeIndex(bad)).toThrow(/name/);
  });

  it('throws when a state has an invalid bbox', () => {
    const bad = loadGolden() as Record<string, unknown>;
    const states = bad.states as Record<string, unknown>[];
    states[0].bbox = [1, 2, 3]; // too few elements
    expect(() => parseCompositeIndex(bad)).toThrow(/bbox/);
  });

  it('throws on a non-object root', () => {
    expect(() => parseCompositeIndex(null)).toThrow(/index/);
  });
});
