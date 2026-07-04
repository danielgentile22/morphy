/**
 * OwnerFeatures — the single owner-column vocabulary the app's client reads.
 *
 * The filter predicate (filter-model.ts) and the scorer (scoring.ts) both read
 * owner columns; the slim owners index (owners-filter-index.ts) coerces them
 * from JSON; the filter sliders and the scorer both normalize against the same
 * per-column maxima. This module owns all three — the column list, the JSON
 * coercion, and the one O(N) extents pass — so they can't drift. Add a column
 * here + at its one use site (a FILTER_FIELDS row / a SCORE_FEATURES entry) and
 * the interface, the coercion, and the extents all follow.
 *
 * The column list is kept in sync with the owners-index schema by hand;
 * generating it from the schema (cross-language) is out of scope (PRD #253).
 */

/** Every owner-feature column the client reads (filter + scoring). */
export interface OwnerFeatures {
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

// ── JSON coercion ───────────────────────────────────────────────────────────

export function coerceStrList(v: unknown): string[] {
  return Array.isArray(v) ? v.map(String) : [];
}

export function coerceNum(v: unknown, fallback = 0): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

/** Coerce one raw JSON owner into typed feature columns (tolerant of a
 *  stale/partial index — missing filter fields degrade to "no constraint"
 *  values). Identity fields (display_cluster_id, owner_name, …) are the slim
 *  index's own concern; this owns only the shared feature columns. */
export function coerceOwnerFeatures(o: Record<string, unknown>): OwnerFeatures {
  return {
    owner_kind: String(o.owner_kind ?? ''),
    states: coerceStrList(o.states),
    counties: coerceStrList(o.counties),
    distress_tier: String(o.distress_tier ?? ''),
    in_oz: o.in_oz === true,
    in_qct: o.in_qct === true,
    persistent_poverty: o.persistent_poverty === true,
    score: coerceNum(o.score),
    parcel_count: coerceNum(o.parcel_count),
    tower_count: coerceNum(o.tower_count),
    solar_count: coerceNum(o.solar_count),
    structure_count: coerceNum(o.structure_count),
    structure_types: coerceStrList(o.structure_types),
    active_tower_count: coerceNum(o.active_tower_count),
    total_assessed_value: coerceNum(o.total_assessed_value),
    tallest_tower_height_m:
      o.tallest_tower_height_m == null ? null : coerceNum(o.tallest_tower_height_m, 0),
    carrier_count: coerceNum(o.carrier_count),
  };
}

// ── extents (one pass over the index) ───────────────────────────────────────

/**
 * Per-column maxima across the loaded owners index — ONE O(N) pass feeding both
 * the filter sliders (filter-model.svelte) and the scorer's normalization
 * (scoring-store). Raw maxima with the natural per-column floor; each consumer
 * applies its own rounding/floor on top (the filter ceils its slider bounds;
 * the scorer floors height at 1 to avoid a zero normalizer).
 */
export interface OwnerExtents {
  /** max total_assessed_value (floor 0). */
  assessedMax: number;
  /** max parcel_count (floor 1). */
  portfolioMax: number;
  /** max tallest_tower_height_m (floor 0). */
  heightMax: number;
  /** max structure_count (floor 1). */
  structureCountMax: number;
  /** max tower_count (floor 1). */
  towerMax: number;
  /** max carrier_count (floor 1). */
  carrierMax: number;
}

export function computeOwnerExtents(owners: readonly OwnerFeatures[]): OwnerExtents {
  let assessedMax = 0;
  let portfolioMax = 1;
  let heightMax = 0;
  let structureCountMax = 1;
  let towerMax = 1;
  let carrierMax = 1;
  for (const o of owners) {
    if (o.total_assessed_value > assessedMax) assessedMax = o.total_assessed_value;
    if (o.parcel_count > portfolioMax) portfolioMax = o.parcel_count;
    const h = o.tallest_tower_height_m ?? 0;
    if (h > heightMax) heightMax = h;
    if (o.structure_count > structureCountMax) structureCountMax = o.structure_count;
    if (o.tower_count > towerMax) towerMax = o.tower_count;
    if (o.carrier_count > carrierMax) carrierMax = o.carrier_count;
  }
  return { assessedMax, portfolioMax, heightMax, structureCountMax, towerMax, carrierMax };
}
