/**
 * The shared, lead-centric FilterModel (Slice 6 / #52).
 *
 * ONE filter state narrows BOTH surfaces: the structures-first map's tower
 * layer and the Candidates list. To guarantee they can't drift, every filter
 * is described once in `FILTER_FIELDS` and projected two ways:
 *
 *   - `composeOwnerWhere(model)` → a deterministic SQL WHERE-clause body over
 *     the owners-index columns. This is the canonical query contract — the
 *     unit tests assert it byte-for-byte (mirroring the parcel-layer `query.ts`).
 *   - `matchesOwner(owner, model)` → the runtime predicate. The map builds the
 *     set of matching `display_cluster_id`s with it (then keeps only those
 *     towers); the Candidates list filters its owner rows with it.
 *
 * Both come from the same `FILTER_FIELDS` registry, so the SQL and the
 * predicate are the same logic by construction (a consistency test pins it).
 *
 * Filter set (ADR-061): State (multi, OR), distress (ARC tier + OZ/QCT/
 * persistent-poverty), structure type, interestingness score (min); plus the
 * "More" long tail — owner kind, portfolio size, total assessed value (range),
 * county, tower height (min), active-only, structure count (min). Acreage and
 * raw "has tower" are deliberately gone (they were parcel-level noise).
 *
 * Sentinels for "no constraint": empty array / null / false; the numeric
 * thresholds have a natural floor (`scoreMin`/`heightMin` 0, `portfolioMin`/
 * `structureCountMin` 1), declared per-spec via `noOpAt`.
 */

import { sqlNumber, sqlString } from './filters';

/** The owner-index fields the predicate reads. Both the slim client filter
 *  index (`owners_filter.json`) and the backend `OwnerSummary` satisfy this,
 *  so one predicate filters both surfaces. */
export interface FilterableOwner {
  states: string[];
  counties: string[];
  owner_kind: string;
  distress_tier: string;
  in_oz: boolean;
  in_qct: boolean;
  persistent_poverty: boolean;
  score: number;
  parcel_count: number;
  total_assessed_value: number;
  tower_count: number;
  solar_count: number;
  structure_count: number;
  structure_types: string[];
  active_tower_count: number;
  tallest_tower_height_m: number | null;
  carrier_count: number;
}

export interface FilterModel {
  /** Anchor-state abbreviations; OR (an owner with a holding in ANY matches). */
  states: string[];
  /** ARC distress tier values (e.g. 'distressed', 'at-risk'). */
  distressTiers: string[];
  /** Owner kind (llc / individual / trust / gov / …). */
  ownerKinds: string[];
  /** County FIPS (5-digit); OR across the owner's holdings. */
  countyFips: string[];
  /** Structure types the owner must host one of — subset of {tower, solar}. */
  structureTypes: string[];
  inOz: boolean;
  inQct: boolean;
  persistentPoverty: boolean;
  /** Keep only owners with ≥1 active tower. */
  activeOnly: boolean;
  /** interestingness score ≥ this (0 = no constraint) — a MINIMUM threshold. */
  scoreMin: number;
  /** portfolio size (parcel_count) ≥ this (1 = no constraint). */
  portfolioMin: number;
  /** tallest tower height in metres ≥ this (0 = no constraint). */
  heightMin: number;
  /** structure_count ≥ this (1 = no constraint). */
  structureCountMin: number;
  /** total assessed value within [min, max], or null for no constraint. */
  assessedValue: [number, number] | null;
}

/** A fresh, fully-unconstrained filter model. */
export function emptyFilterModel(): FilterModel {
  return {
    states: [],
    distressTiers: [],
    ownerKinds: [],
    countyFips: [],
    structureTypes: [],
    inOz: false,
    inQct: false,
    persistentPoverty: false,
    activeOnly: false,
    scoreMin: 0,
    portfolioMin: 1,
    heightMin: 0,
    structureCountMin: 1,
    assessedValue: null,
  };
}

// ── FilterField — one descriptor per FilterModel field ──────────────────────

interface FilterField {
  readonly id: keyof FilterModel;
  readonly column: string;
  readonly isActive: (m: FilterModel) => boolean;
  /** SQL WHERE fragment over the owner-index column, or null when inactive. */
  readonly toSQL: (m: FilterModel) => string | null;
  /** Runtime predicate fragment. Only consulted when `isActive`. */
  readonly test: (o: FilterableOwner, m: FilterModel) => boolean;
}

/** `[a, b, c]` SQL list literal (DuckDB) — used by the OR/`list_has_any` specs. */
function sqlList(values: string[]): string {
  return `[${values.map(sqlString).join(', ')}]`;
}

/** Scalar-column "value ∈ selected" (OR). e.g. owner_kind, distress_tier. */
function inSetField(
  id: keyof FilterModel,
  column: string,
  get: (o: FilterableOwner) => string,
): FilterField {
  return {
    id,
    column,
    isActive: (m) => (m[id] as string[]).length > 0,
    toSQL: (m) => {
      const v = m[id] as string[];
      return v.length ? `${column} IN (${v.map(sqlString).join(', ')})` : null;
    },
    test: (o, m) => (m[id] as string[]).includes(get(o)),
  };
}

/** List-column overlap "owner's list intersects selected" (OR). e.g. states. */
function listOverlapField(
  id: keyof FilterModel,
  column: string,
  get: (o: FilterableOwner) => string[],
): FilterField {
  return {
    id,
    column,
    isActive: (m) => (m[id] as string[]).length > 0,
    toSQL: (m) => {
      const v = m[id] as string[];
      return v.length ? `list_has_any(${column}, ${sqlList(v)})` : null;
    },
    test: (o, m) => {
      const sel = m[id] as string[];
      return get(o).some((x) => sel.includes(x));
    },
  };
}

function boolField(
  id: keyof FilterModel,
  column: string,
  sql: string,
  get: (o: FilterableOwner) => boolean,
): FilterField {
  return {
    id,
    column,
    isActive: (m) => Boolean(m[id]),
    toSQL: (m) => (m[id] ? sql : null),
    test: (o) => get(o),
  };
}

function minField(
  id: keyof FilterModel,
  column: string,
  noOpAt: number,
  get: (o: FilterableOwner) => number,
): FilterField {
  return {
    id,
    column,
    isActive: (m) => (m[id] as number) > noOpAt,
    toSQL: (m) => {
      const v = m[id] as number;
      return v > noOpAt ? `${column} >= ${sqlNumber(v)}` : null;
    },
    test: (o, m) => get(o) >= (m[id] as number),
  };
}

function rangeField(
  id: keyof FilterModel,
  column: string,
  get: (o: FilterableOwner) => number,
): FilterField {
  return {
    id,
    column,
    isActive: (m) => m[id] !== null,
    toSQL: (m) => {
      const r = m[id] as [number, number] | null;
      return r === null ? null : `${column} BETWEEN ${sqlNumber(r[0])} AND ${sqlNumber(r[1])}`;
    },
    test: (o, m) => {
      const r = m[id] as [number, number] | null;
      if (r === null) return true;
      const v = get(o);
      return v >= r[0] && v <= r[1];
    },
  };
}

/**
 * The whole filter vocabulary, in the order WHERE-clauses are emitted.
 * Stable so `composeOwnerWhere` output is deterministic — the unit tests
 * assert exact strings.
 */
export const FILTER_FIELDS: readonly FilterField[] = [
  listOverlapField('states', 'states', (o) => o.states),
  inSetField('distressTiers', 'distress_tier', (o) => o.distress_tier),
  inSetField('ownerKinds', 'owner_kind', (o) => o.owner_kind),
  listOverlapField('countyFips', 'counties', (o) => o.counties),
  listOverlapField('structureTypes', 'structure_types', (o) => o.structure_types),
  boolField('inOz', 'in_oz', 'in_oz', (o) => o.in_oz),
  boolField('inQct', 'in_qct', 'in_qct', (o) => o.in_qct),
  boolField('persistentPoverty', 'persistent_poverty', 'persistent_poverty', (o) => o.persistent_poverty),
  boolField('activeOnly', 'active_tower_count', 'active_tower_count > 0', (o) => o.active_tower_count > 0),
  minField('scoreMin', 'score', 0, (o) => o.score),
  minField('portfolioMin', 'parcel_count', 1, (o) => o.parcel_count),
  minField('heightMin', 'tallest_tower_height_m', 0, (o) => o.tallest_tower_height_m ?? 0),
  minField('structureCountMin', 'structure_count', 1, (o) => o.structure_count),
  rangeField('assessedValue', 'total_assessed_value', (o) => o.total_assessed_value),
];

// ── projections ─────────────────────────────────────────────────────────────

/** The canonical SQL WHERE-clause body for a filter model — `''` when nothing
 *  is filtered. Clauses are AND-ed in FILTER_FIELDS order (deterministic). */
export function composeOwnerWhere(m: FilterModel): string {
  const clauses: string[] = [];
  for (const f of FILTER_FIELDS) {
    const frag = f.toSQL(m);
    if (frag !== null) clauses.push(frag);
  }
  return clauses.join(' AND ');
}

/** True when this owner passes every active filter. Empty model ⇒ all owners. */
export function matchesOwner(o: FilterableOwner, m: FilterModel): boolean {
  for (const f of FILTER_FIELDS) {
    if (f.isActive(m) && !f.test(o, m)) return false;
  }
  return true;
}

/** True when at least one filter constrains the result set. */
export function isAnyFilterActive(m: FilterModel): boolean {
  return FILTER_FIELDS.some((f) => f.isActive(m));
}

/** How many filter controls are currently constraining the result. */
export function activeFilterCount(m: FilterModel): number {
  return FILTER_FIELDS.reduce((n, f) => n + (f.isActive(m) ? 1 : 0), 0);
}

// ── personal filter default (PRD #121) ────────────────────────────────────────
// A saved "default filters" snapshot is an opaque JSON blob the backend stores
// per user (see UserSettingsStore) and serves back verbatim. We serialise only
// the fields that differ from the empty model — same shape as the URL `filters`
// param (url.ts) — so a snapshot is forward-compatible (a new field absent from
// an old snapshot just keeps its default on restore).

/** Serialise a model to its stored snapshot — non-default fields only. */
export function serializeFilterModel(m: FilterModel): string {
  const defaults = emptyFilterModel();
  const active: Record<string, unknown> = {};
  for (const key of Object.keys(defaults) as (keyof FilterModel)[]) {
    if (JSON.stringify(m[key]) !== JSON.stringify(defaults[key])) active[key] = m[key];
  }
  return JSON.stringify(active);
}

/** Restore a snapshot, merging known keys onto the defaults. Malformed JSON (or
 *  a non-object) yields the empty model rather than throwing. */
export function deserializeFilterModel(json: string): FilterModel {
  const result = emptyFilterModel();
  try {
    const parsed: unknown = JSON.parse(json);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const obj = parsed as Record<string, unknown>;
      const target = result as unknown as Record<string, unknown>;
      for (const key of Object.keys(result)) {
        if (key in obj) target[key] = obj[key];
      }
    }
  } catch {
    // malformed snapshot — fall back to no filters
  }
  return result;
}

/** Whether to auto-apply a personal default when Explore opens. A shared deep
 *  link carrying its own filters always wins, so the default applies only when
 *  the URL has no filter params *and* the user opted in. */
export function shouldApplyFilterDefault(urlHasFilters: boolean, applyPref: boolean): boolean {
  return applyPref && !urlHasFilters;
}

/** A short, human-readable summary of the active filters in a model — for the
 *  "Filter defaults" settings card, so the user can see what their saved
 *  default will apply. Empty array ⇒ no filters (opens unfiltered). */
export function summarizeFilterModel(m: FilterModel): string[] {
  const out: string[] = [];
  if (m.states.length) out.push(`States: ${m.states.join(', ')}`);
  if (m.distressTiers.length) out.push(`Distress: ${m.distressTiers.join(', ')}`);
  if (m.ownerKinds.length) out.push(`Owner type: ${m.ownerKinds.join(', ')}`);
  if (m.countyFips.length) out.push(`Counties: ${m.countyFips.length}`);
  if (m.structureTypes.length) out.push(`Structure: ${m.structureTypes.join(', ')}`);
  if (m.inOz) out.push('In Opportunity Zone');
  if (m.inQct) out.push('In QCT');
  if (m.persistentPoverty) out.push('Persistent poverty');
  if (m.activeOnly) out.push('Active towers only');
  if (m.scoreMin > 0) out.push(`Score ≥ ${m.scoreMin}`);
  if (m.portfolioMin > 1) out.push(`Parcels ≥ ${m.portfolioMin}`);
  if (m.heightMin > 0) out.push(`Height ≥ ${m.heightMin} m`);
  if (m.structureCountMin > 1) out.push(`Structures ≥ ${m.structureCountMin}`);
  if (m.assessedValue) out.push(`Market $${m.assessedValue[0]}–$${m.assessedValue[1]}`);
  return out;
}
