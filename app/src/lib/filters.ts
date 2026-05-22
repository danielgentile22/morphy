/**
 * Parcel filter state.
 *
 * One typed object describes every filter control. It is composed into
 * SQL by ./query and applied to the map by the store. Numeric "no
 * constraint" sentinels: `scoreMin` 0, `clusterSizeMin` 1, range filters
 * `null`.
 */

export interface FilterState {
  ownerKind: string[];
  distressTier: string[];
  landUse: string[];
  countyFips: string[];
  hasTower: boolean;
  hasSolar: boolean;
  hasBillboard: boolean;
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
    landUse: [],
    countyFips: [],
    hasTower: false,
    hasSolar: false,
    hasBillboard: false,
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

/** True when at least one filter constrains the result set. */
export function isAnyFilterActive(f: FilterState): boolean {
  return activeFilterCount(f) > 0;
}

/** How many filter controls are currently constraining the result. */
export function activeFilterCount(f: FilterState): number {
  let n = 0;
  if (f.ownerKind.length) n++;
  if (f.distressTier.length) n++;
  if (f.landUse.length) n++;
  if (f.countyFips.length) n++;
  if (f.hasTower) n++;
  if (f.hasSolar) n++;
  if (f.hasBillboard) n++;
  if (f.inOz) n++;
  if (f.inQct) n++;
  if (f.persistentPoverty) n++;
  if (f.scoreMin > 0) n++;
  if (f.clusterSizeMin > 1) n++;
  if (f.assessedValue) n++;
  if (f.acreage) n++;
  if (f.ownerClusterId) n++;
  return n;
}
