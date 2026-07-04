import { describe, it, expect } from 'vitest';
import { parseCompositeIndex } from '../../src/lib/catalog';

// Minimal raw shape mirroring the real index.json.
const RAW_INDEX = {
  schema_version: 1,
  generated_at: '2026-05-21T17:17:59+00:00',
  states: [
    {
      fips: '05',
      abbr: 'AR',
      name: 'Arkansas',
      bbox: [-94.62, 33.0, -89.64, 36.5],
      counts: { parcel: 2116976, tower: 15846, bogus: 'x' },
    },
    {
      fips: '30',
      abbr: 'MT',
      name: 'Montana',
      bbox: [-116.06, 44.36, -104.04, 49.0],
      counts: { parcel: 920111 },
    },
  ],
};

describe('parseCompositeIndex', () => {
  it('parses a valid index', () => {
    const idx = parseCompositeIndex(RAW_INDEX);
    expect(idx.schemaVersion).toBe(1);
    expect(idx.states).toHaveLength(2);
    expect(idx.states[0]).toMatchObject({ fips: '05', abbr: 'AR', name: 'Arkansas' });
    expect(idx.states[0].bbox).toEqual([-94.62, 33.0, -89.64, 36.5]);
  });

  it('keeps only numeric counts', () => {
    const idx = parseCompositeIndex(RAW_INDEX);
    expect(idx.states[0].counts).toEqual({ parcel: 2116976, tower: 15846 });
  });

  it('throws on a non-object root', () => {
    expect(() => parseCompositeIndex(null)).toThrow(/index/);
    expect(() => parseCompositeIndex('nope')).toThrow(/index/);
  });

  it('throws when the states array is missing', () => {
    expect(() =>
      parseCompositeIndex({ schema_version: 1, generated_at: '' }),
    ).toThrow(/states/);
  });

  it('throws when a state has an invalid bbox', () => {
    const bad = {
      schema_version: 1,
      generated_at: '',
      states: [{ fips: '05', abbr: 'AR', name: 'Arkansas', bbox: [1, 2, 3] }],
    };
    expect(() => parseCompositeIndex(bad)).toThrow(/bbox/);
  });

  it('throws when a state is missing its fips', () => {
    const bad = {
      schema_version: 1,
      generated_at: '',
      states: [{ abbr: 'AR', bbox: [-94, 33, -89, 36] }],
    };
    expect(() => parseCompositeIndex(bad)).toThrow(/fips/);
  });
});
