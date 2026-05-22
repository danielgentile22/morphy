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

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}
function asString(v: unknown): string {
  return typeof v === 'string' ? v : '';
}
function asNumber(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0;
}
function optString(v: unknown): string | undefined {
  return typeof v === 'string' && v !== '' ? v : undefined;
}
function stringMap(v: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (isRecord(v)) for (const [k, val] of Object.entries(v)) out[k] = asString(val);
  return out;
}

// ── index.json parser ────────────────────────────────────────────────────

function parseStateEntry(raw: unknown, i: number): StateEntry {
  if (!isRecord(raw)) throw new Error(`index.json: states[${i}] is not an object`);
  const fips = asString(raw.fips);
  if (!fips) throw new Error(`index.json: states[${i}] is missing "fips"`);
  if (!isValidBBox(raw.bbox)) {
    throw new Error(`index.json: state ${fips} has an invalid "bbox"`);
  }
  const counts: Record<string, number> = {};
  if (isRecord(raw.counts)) {
    for (const [k, v] of Object.entries(raw.counts)) {
      if (typeof v === 'number') counts[k] = v;
    }
  }
  return {
    fips,
    abbr: asString(raw.abbr) || fips,
    name: asString(raw.name) || fips,
    bbox: raw.bbox,
    counts,
  };
}

export function parseCompositeIndex(raw: unknown): CompositeIndex {
  if (!isRecord(raw)) throw new Error('index.json: root is not an object');
  if (!Array.isArray(raw.states)) {
    throw new Error('index.json: missing "states" array');
  }
  return {
    schemaVersion: asNumber(raw.schema_version),
    generatedAt: asString(raw.generated_at),
    states: raw.states.map(parseStateEntry),
  };
}

// ── catalog.json parser ──────────────────────────────────────────────────

function parseLayer(name: string, raw: unknown): CatalogLayer {
  if (!isRecord(raw)) throw new Error(`catalog.json: layer "${name}" is not an object`);
  return {
    name,
    canonicalType: asString(raw.canonical_type),
    rows: asNumber(raw.rows),
    parquetPath: asString(raw.parquet_path),
    geojsonPath: optString(raw.geojson_path),
    simplifiedGeojsonPath: optString(raw.simplified_geojson_path),
    geometryType: optString(raw.geometry_type),
    schema: stringMap(raw.schema),
  };
}

function parseView(name: string, raw: unknown): CatalogView {
  if (!isRecord(raw)) throw new Error(`catalog.json: view "${name}" is not an object`);
  return {
    name,
    description: asString(raw.description),
    geometryType: typeof raw.geometry_type === 'string' ? raw.geometry_type : null,
    inputs: Array.isArray(raw.inputs) ? raw.inputs.map(asString) : [],
    parquetPath: asString(raw.parquet_path),
    geojsonPath: optString(raw.geojson_path),
    rows: asNumber(raw.rows),
  };
}

export function parseCatalog(raw: unknown): Catalog {
  if (!isRecord(raw)) throw new Error('catalog.json: root is not an object');
  const stateFips = asString(raw.state_fips);
  if (!stateFips) throw new Error('catalog.json: missing "state_fips"');

  const layers: CatalogLayer[] = [];
  if (isRecord(raw.layers)) {
    for (const [name, v] of Object.entries(raw.layers)) layers.push(parseLayer(name, v));
  }
  const views: CatalogView[] = [];
  if (isRecord(raw.views)) {
    for (const [name, v] of Object.entries(raw.views)) views.push(parseView(name, v));
  }
  return {
    schemaVersion: asNumber(raw.schema_version),
    stateFips,
    stateName: asString(raw.state_name),
    stateAbbr: asString(raw.state_abbr),
    generatedAt: asString(raw.generated_at),
    layers,
    views,
    sourcesUsedVersions: stringMap(raw.sources_used_versions),
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
