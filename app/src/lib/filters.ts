/**
 * Parcel filter state + the FilterSpec registry that drives every
 * dispatch operation (active-check, SQL composition, count).
 *
 * `FilterState` is a typed flat record — Svelte components and the URL
 * serializer rely on field-level type access. The per-filter dispatch
 * logic (when a control is constraining, what SQL it emits) lives in
 * `FILTER_SPECS` — one entry per FilterState field. Adding a new filter
 * is three small touches in this file (field, default, spec) plus one
 * bespoke control in FilterPanel.svelte; no other file changes.
 *
 * Sentinels for "no constraint":
 *   - empty array / null / false
 *   - `scoreMin = 0`, `clusterSizeMin = 1` (numeric thresholds with a
 *     natural floor); declared via the spec's `noOpAt`.
 */

// ── SQL-literal primitives ──────────────────────────────────────────────
// Shared by the FilterSpec registry below and by the outer query
// builders in `./query`. Lives here so callers have one import.

/** Escape a string as a SQL literal — wraps in single quotes, doubles internal quotes. */
export function sqlString(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

/** Render a finite number as a SQL literal; throw on NaN/Infinity. */
export function sqlNumber(n: number): string {
  if (!Number.isFinite(n)) throw new Error(`non-finite number in a filter: ${n}`);
  return String(n);
}

export interface FilterState {
  ownerKind: string[];
  distressTier: string[];
  countyFips: string[];
  hasTower: boolean;
  hasSolar: boolean;
  inOz: boolean;
  inQct: boolean;
  persistentPoverty: boolean;
  /** interestingness_score ≥ this (0 = no constraint). */
  scoreMin: number;
  /** owner_cluster_size ≥ this (1 = no constraint). */
  clusterSizeMin: number;
  /** assessed_value within [min, max], or null for no constraint. */
  assessedValue: [number, number] | null;
  /** acreage within [min, max], or null for no constraint. */
  acreage: [number, number] | null;
  /** owner_cluster_id = this — set by owner search / "see all parcels". */
  ownerClusterId: string | null;
}

/** A fresh, fully-unconstrained filter state. */
export function emptyFilters(): FilterState {
  return {
    ownerKind: [],
    distressTier: [],
    countyFips: [],
    hasTower: false,
    hasSolar: false,
    inOz: false,
    inQct: false,
    persistentPoverty: false,
    scoreMin: 0,
    clusterSizeMin: 1,
    assessedValue: null,
    acreage: null,
    ownerClusterId: null,
  };
}

// ── FilterSpec — one descriptor per FilterState field ───────────────────

/** One filter's worth of dispatch: active-check + SQL generator. */
export interface FilterSpec {
  /** The FilterState key this spec owns. Also the URL serialization key. */
  readonly id: keyof FilterState;
  /** The SQL column name the spec emits against. */
  readonly column: string;
  /** True when the filter is constraining the result set. */
  readonly isActive: (s: FilterState) => boolean;
  /** SQL WHERE-clause fragment, or null when not active. */
  readonly toSQL: (s: FilterState) => string | null;
}

// Type-level helper: which FilterState keys hold a given value type?
// Used by the spec builders to enforce that e.g. `booleanSpec` is only
// applied to boolean fields — a typo like `booleanSpec('scoreMin', …)`
// fails to compile.
type FieldsOfType<T> = {
  [K in keyof FilterState]: FilterState[K] extends T ? K : never;
}[keyof FilterState];

function inSetSpec<K extends FieldsOfType<string[]>>(id: K, column: string): FilterSpec {
  return {
    id,
    column,
    isActive: (s) => (s[id] as string[]).length > 0,
    toSQL: (s) => {
      const values = s[id] as string[];
      if (values.length === 0) return null;
      return `${column} IN (${values.map(sqlString).join(', ')})`;
    },
  };
}

function booleanSpec<K extends FieldsOfType<boolean>>(id: K, column: string): FilterSpec {
  return {
    id,
    column,
    isActive: (s) => Boolean(s[id]),
    toSQL: (s) => (s[id] ? column : null),
  };
}

function minSpec<K extends FieldsOfType<number>>(
  id: K,
  column: string,
  opts: { noOpAt: number },
): FilterSpec {
  return {
    id,
    column,
    isActive: (s) => (s[id] as number) > opts.noOpAt,
    toSQL: (s) => {
      const v = s[id] as number;
      return v > opts.noOpAt ? `${column} >= ${sqlNumber(v)}` : null;
    },
  };
}

function rangeSpec<K extends FieldsOfType<[number, number] | null>>(
  id: K,
  column: string,
): FilterSpec {
  return {
    id,
    column,
    isActive: (s) => s[id] !== null,
    toSQL: (s) => {
      const range = s[id] as [number, number] | null;
      if (range === null) return null;
      return `${column} BETWEEN ${sqlNumber(range[0])} AND ${sqlNumber(range[1])}`;
    },
  };
}

function exactSpec<K extends FieldsOfType<string | null>>(id: K, column: string): FilterSpec {
  return {
    id,
    column,
    isActive: (s) => s[id] !== null,
    toSQL: (s) => {
      const v = s[id] as string | null;
      return v === null ? null : `${column} = ${sqlString(v)}`;
    },
  };
}

/**
 * The whole filter vocabulary, in the order WHERE-clauses are emitted.
 * Ordering is stable so `composeWhere` output is deterministic — the
 * unit tests assert exact strings.
 */
export const FILTER_SPECS: readonly FilterSpec[] = [
  inSetSpec('ownerKind', 'owner_kind'),
  inSetSpec('distressTier', 'distress_tier'),
  inSetSpec('countyFips', 'county_fips'),
  booleanSpec('hasTower', 'has_tower'),
  booleanSpec('hasSolar', 'has_solar'),
  booleanSpec('inOz', 'in_oz'),
  booleanSpec('inQct', 'in_qct'),
  booleanSpec('persistentPoverty', 'persistent_poverty'),
  minSpec('scoreMin', 'interestingness_score', { noOpAt: 0 }),
  minSpec('clusterSizeMin', 'owner_cluster_size', { noOpAt: 1 }),
  rangeSpec('assessedValue', 'assessed_value'),
  rangeSpec('acreage', 'acreage'),
  exactSpec('ownerClusterId', 'owner_cluster_id'),
];

// ── Aggregate dispatch ──────────────────────────────────────────────────

/** True when at least one filter constrains the result set. */
export function isAnyFilterActive(f: FilterState): boolean {
  return FILTER_SPECS.some((spec) => spec.isActive(f));
}

/** How many filter controls are currently constraining the result. */
export function activeFilterCount(f: FilterState): number {
  return FILTER_SPECS.reduce((n, spec) => n + (spec.isActive(f) ? 1 : 0), 0);
}
