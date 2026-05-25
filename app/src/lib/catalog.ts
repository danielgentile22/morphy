/**
 * Types + parsers for the two data-contract files the app binds to:
 *   - composite/index.json   — the global state list (rehaul choice 1)
 *   - composite/<fips>/catalog.json — the per-state layer/view manifest
 *
 * The app binds to the *catalog*, never to a hardcoded state — any
 * future composed state appears with zero app changes. Parsers convert
 * the snake_case JSON into camelCase domain objects and throw a clear,
 * prefixed Error on malformed input, so a bad file surfaces as an
 * actionable message instead of a downstream crash.
 */

import { isValidBBox, type BBox } from './geo';
import type { EntityKind } from './schema';

// ── index.json ───────────────────────────────────────────────────────────

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

// ── catalog.json ─────────────────────────────────────────────────────────

/** A composite layer (towers, parcels, distress_overlays, …). */
export interface CatalogLayer {
  name: string;
  canonicalType: string;
  rows: number;
  parquetPath: string;
  geojsonPath?: string;
  simplifiedGeojsonPath?: string;
  geometryType?: string;
  schema: Record<string, string>;
}

/** A derived view (interestingness_top_1000, owner_clusters, …). */
export interface CatalogView {
  name: string;
  description: string;
  geometryType: string | null;
  inputs: string[];
  parquetPath: string;
  geojsonPath?: string;
  rows: number;
}

export interface Catalog {
  schemaVersion: number;
  stateFips: string;
  stateName: string;
  stateAbbr: string;
  generatedAt: string;
  layers: CatalogLayer[];
  views: CatalogView[];
  sourcesUsedVersions: Record<string, string>;
}

// ── guards ───────────────────────────────────────────────────────────────
//
// The Python writer validates its output against `catalog.schema.json`
// before write (see scripts/preprocess/catalog_schema.py). The parsers
// below mirror that contract on the read side: missing required fields
// THROW, not coerce — silent coercion masks bugs that surface as
// "missing layers" in production. Optional fields are explicitly typed
// as such and tolerated when absent.

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function requireString(v: unknown, path: string): string {
  // Accept empty strings — the schema allows them where there's no
  // explicit minLength, and the Python side enforces minLength when set.
  // The TS parser only enforces the type, not the length.
  if (typeof v !== 'string') {
    throw new Error(`catalog: missing or non-string required field "${path}"`);
  }
  return v;
}

function requireInteger(v: unknown, path: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v) || !Number.isInteger(v) || v < 0) {
    throw new Error(`catalog: missing or non-integer required field "${path}"`);
  }
  return v;
}

function requireStringArray(v: unknown, path: string): string[] {
  if (!Array.isArray(v) || !v.every((x) => typeof x === 'string')) {
    throw new Error(`catalog: missing or non-string-array required field "${path}"`);
  }
  return v as string[];
}

function optionalString(v: unknown, path: string): string | undefined {
  if (v === undefined) return undefined;
  if (typeof v !== 'string') {
    throw new Error(`catalog: optional field "${path}" is present but not a string`);
  }
  return v.length === 0 ? undefined : v;
}

function requireStringMap(v: unknown, path: string): Record<string, string> {
  if (!isRecord(v)) {
    throw new Error(`catalog: missing or non-object required field "${path}"`);
  }
  const out: Record<string, string> = {};
  for (const [k, val] of Object.entries(v)) {
    if (typeof val !== 'string') {
      throw new Error(`catalog: "${path}.${k}" is not a string`);
    }
    out[k] = val;
  }
  return out;
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

// ── catalog.json parser ──────────────────────────────────────────────────

function parseLayer(name: string, raw: unknown): CatalogLayer {
  if (!isRecord(raw)) throw new Error(`catalog: layer "${name}" is not an object`);
  return {
    name,
    canonicalType: requireString(raw.canonical_type, `layers.${name}.canonical_type`),
    rows: requireInteger(raw.rows, `layers.${name}.rows`),
    parquetPath: requireString(raw.parquet_path, `layers.${name}.parquet_path`),
    geojsonPath: optionalString(raw.geojson_path, `layers.${name}.geojson_path`),
    simplifiedGeojsonPath: optionalString(
      raw.simplified_geojson_path,
      `layers.${name}.simplified_geojson_path`,
    ),
    // geometry_type is optional, and empty-string is meaningful ("no
    // detectable type"). We keep it as undefined when missing/empty
    // so consumers don't have to special-case "".
    geometryType: optionalString(raw.geometry_type, `layers.${name}.geometry_type`),
    schema: requireStringMap(raw.schema, `layers.${name}.schema`),
  };
}

function parseView(name: string, raw: unknown): CatalogView {
  if (!isRecord(raw)) throw new Error(`catalog: view "${name}" is not an object`);
  // geometry_type on a view is required (per the schema) but is nullable
  // — null distinguishes a tabular view from a spatial one.
  if (raw.geometry_type !== null && typeof raw.geometry_type !== 'string') {
    throw new Error(`catalog: views.${name}.geometry_type must be a string or null`);
  }
  return {
    name,
    description: requireString(raw.description, `views.${name}.description`),
    geometryType: raw.geometry_type as string | null,
    inputs: requireStringArray(raw.inputs, `views.${name}.inputs`),
    parquetPath: requireString(raw.parquet_path, `views.${name}.parquet_path`),
    geojsonPath: optionalString(raw.geojson_path, `views.${name}.geojson_path`),
    rows: requireInteger(raw.rows, `views.${name}.rows`),
  };
}

export function parseCatalog(raw: unknown): Catalog {
  if (!isRecord(raw)) throw new Error('catalog: root is not an object');
  if (!isRecord(raw.layers)) throw new Error('catalog: missing required field "layers"');
  if (!isRecord(raw.views)) throw new Error('catalog: missing required field "views"');

  const layers: CatalogLayer[] = [];
  for (const [name, v] of Object.entries(raw.layers)) layers.push(parseLayer(name, v));
  const views: CatalogView[] = [];
  for (const [name, v] of Object.entries(raw.views)) views.push(parseView(name, v));

  return {
    schemaVersion: requireInteger(raw.schema_version, 'schema_version'),
    stateFips: requireString(raw.state_fips, 'state_fips'),
    stateName: requireString(raw.state_name, 'state_name'),
    stateAbbr: requireString(raw.state_abbr, 'state_abbr'),
    generatedAt: requireString(raw.generated_at, 'generated_at'),
    layers,
    views,
    sourcesUsedVersions: requireStringMap(raw.sources_used_versions, 'sources_used_versions'),
  };
}

// ── convenience selectors ────────────────────────────────────────────────

/** Layers that carry a GeoJSON file (renderable in Phase A without tiles). */
export function geojsonLayers(catalog: Catalog): CatalogLayer[] {
  return catalog.layers.filter((l) => l.geojsonPath);
}

/** Views that carry a GeoJSON file (toggleable overlays). */
export function geojsonViews(catalog: Catalog): CatalogView[] {
  return catalog.views.filter((v) => v.geojsonPath);
}

export function findLayer(catalog: Catalog, name: string): CatalogLayer | undefined {
  return catalog.layers.find((l) => l.name === name);
}

export function findView(catalog: Catalog, name: string): CatalogView | undefined {
  return catalog.views.find((v) => v.name === name);
}

function canonicalToKind(canonicalType: string): EntityKind | null {
  switch (canonicalType) {
    case 'tower':
      return 'tower';
    case 'parcel':
      return 'parcel';
    case 'solar_facility':
      return 'solar';
    case 'distress_overlay':
      return 'distress_overlay';
    default:
      return null;
  }
}

/**
 * The detail-panel entity kind for a layer or view. A layer maps from
 * its `canonical_type`; a view maps from its first declared input
 * (e.g. interestingness_top_1000 has inputs ['parcel']). Returns null
 * for things with no panel (county_score).
 */
export function entityKind(catalog: Catalog, name: string): EntityKind | null {
  const layer = catalog.layers.find((l) => l.name === name);
  if (layer) return canonicalToKind(layer.canonicalType);
  const view = catalog.views.find((v) => v.name === name);
  if (view && view.inputs.length > 0) return canonicalToKind(view.inputs[0]);
  return null;
}
