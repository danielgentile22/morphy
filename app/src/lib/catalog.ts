/**
 * Types + parser for composite/index.json — the global state list the app
 * boots from (rehaul choice 1). Converts the snake_case JSON into camelCase
 * domain objects and throws a clear, prefixed Error on malformed input, so a
 * bad file surfaces as an actionable message instead of a downstream crash.
 */

import { isValidBBox, type BBox } from './geo';

/** One composed state, from composite/index.json. */
export interface StateEntry {
  fips: string;
  abbr: string;
  name: string;
  bbox: BBox;
  counts: Record<string, number>;
}

export interface CompositeIndex {
  schemaVersion: number;
  generatedAt: string;
  states: StateEntry[];
}

// ── guards ───────────────────────────────────────────────────────────────
//
// Missing required fields THROW, not coerce — silent coercion masks bugs that
// would otherwise surface as "missing states" downstream.

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function requireString(v: unknown, path: string): string {
  if (typeof v !== 'string') {
    throw new Error(`index: missing or non-string required field "${path}"`);
  }
  return v;
}

function requireInteger(v: unknown, path: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v) || !Number.isInteger(v) || v < 0) {
    throw new Error(`index: missing or non-integer required field "${path}"`);
  }
  return v;
}

// ── index.json parser ────────────────────────────────────────────────────

function parseStateEntry(raw: unknown, i: number): StateEntry {
  if (!isRecord(raw)) throw new Error(`index: states[${i}] is not an object`);
  const fips = requireString(raw.fips, `states[${i}].fips`);
  if (!isValidBBox(raw.bbox)) {
    throw new Error(`index: state ${fips} has an invalid "bbox"`);
  }
  // counts: integer-valued per the schema. Non-integer entries are
  // dropped (defensive — old data on disk pre-dates the schema, and
  // the per-state UI doesn't break on a missing count badge).
  const counts: Record<string, number> = {};
  if (isRecord(raw.counts)) {
    for (const [k, v] of Object.entries(raw.counts)) {
      if (typeof v === 'number' && Number.isInteger(v)) counts[k] = v;
    }
  }
  return {
    fips,
    abbr: requireString(raw.abbr, `states[${i}].abbr`),
    name: requireString(raw.name, `states[${i}].name`),
    bbox: raw.bbox,
    counts,
  };
}

export function parseCompositeIndex(raw: unknown): CompositeIndex {
  if (!isRecord(raw)) throw new Error('index: root is not an object');
  if (!Array.isArray(raw.states)) {
    throw new Error('index: missing required field "states"');
  }
  return {
    schemaVersion: requireInteger(raw.schema_version, 'schema_version'),
    generatedAt: requireString(raw.generated_at, 'generated_at'),
    states: raw.states.map(parseStateEntry),
  };
}
