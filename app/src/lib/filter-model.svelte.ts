// The shared FilterModel store (Svelte 5 runes) — Slice 6 / #52, extended for
// the tower-grained Explore (#108).
//
// ONE instance of filter state drives BOTH Explore lenses — the map's tower
// layer and the ranked tower list. It owns:
//   - `model`            the live FilterModel (single source of truth)
//   - the slim owners index, loaded once for map filtering + owner search
//   - `matchingClusterIds`  the owner-id set both lenses narrow towers by
//                           (null ⇒ no filter active ⇒ all towers)
//   - `ownerById`           owner record by cid (rank a tower by its owner)
//   - control options + numeric extents, derived from the index
//
// Both lenses narrow by the same `matchingClusterIds` (the map via
// `filterTowers`, the list via `rankedTowerRows`), so they can never fork.

import {
  emptyFilterModel,
  isAnyFilterActive,
  activeFilterCount,
  matchesOwner,
  type FilterModel,
} from './filter-model';
import { loadOwnersFilterIndex, type OwnerFilterRecord } from './owners-filter-index';
import { DISTRESS_TIERS } from './palette';

type Loadable = 'idle' | 'loading' | 'ready' | 'error';

/** Numeric extents (slider bounds) for the range/min controls. */
export interface FilterExtents {
  assessedMax: number;
  portfolioMax: number;
  heightMax: number;
  structureCountMax: number;
}

class FilterModelStore {
  model = $state<FilterModel>(emptyFilterModel());

  /** The slim owners filter index — map filtering + owner search. */
  owners = $state<OwnerFilterRecord[]>([]);
  ownersStatus = $state<Loadable>('idle');
  ownersError = $state<string | null>(null);

  active = $derived(isAnyFilterActive(this.model));
  activeCount = $derived(activeFilterCount(this.model));

  /** Owner-id set the map narrows towers by. `null` when no filter is active
   *  (show every tower) or the index hasn't loaded yet (can't narrow). */
  matchingClusterIds = $derived.by<Set<string> | null>(() => {
    if (!this.active || this.owners.length === 0) return null;
    const ids = new Set<string>();
    for (const o of this.owners) {
      if (matchesOwner(o, this.model)) ids.add(o.display_cluster_id);
    }
    return ids;
  });

  /** Owner record by display_cluster_id — O(1) lookup for the Explore tower
   *  list (rank a tower by its owner's score) + the tower→owner bridge (#108). */
  ownerById = $derived.by(() => {
    const m = new Map<string, OwnerFilterRecord>();
    for (const o of this.owners) m.set(o.display_cluster_id, o);
    return m;
  });

  // ── control options, derived from the loaded index ─────────────────────
  ownerKindOptions = $derived.by(() => uniqueSorted(this.owners.map((o) => o.owner_kind)));

  /** Distress tiers present, in ARC severity order (palette order). */
  distressTierOptions = $derived.by(() => {
    const present = new Set(this.owners.map((o) => o.distress_tier).filter(Boolean));
    return DISTRESS_TIERS.filter((t) => present.has(t));
  });

  /** Distinct county FIPS present across all owners' holdings, sorted. */
  countyOptions = $derived.by(() => {
    const set = new Set<string>();
    for (const o of this.owners) for (const c of o.counties) if (c) set.add(c);
    return [...set].sort();
  });

  extents = $derived.by<FilterExtents>(() => {
    let assessed = 0;
    let portfolio = 1;
    let height = 0;
    let structures = 1;
    for (const o of this.owners) {
      if (o.total_assessed_value > assessed) assessed = o.total_assessed_value;
      if (o.parcel_count > portfolio) portfolio = o.parcel_count;
      if ((o.tallest_tower_height_m ?? 0) > height) height = o.tallest_tower_height_m ?? 0;
      if (o.structure_count > structures) structures = o.structure_count;
    }
    return {
      assessedMax: Math.ceil(assessed),
      portfolioMax: portfolio,
      heightMax: Math.ceil(height),
      structureCountMax: structures,
    };
  });

  /** Load the slim owners index once (idempotent on success / while loading). */
  async load(): Promise<void> {
    if (this.ownersStatus === 'loading' || this.ownersStatus === 'ready') return;
    this.ownersStatus = 'loading';
    this.ownersError = null;
    try {
      this.owners = await loadOwnersFilterIndex();
      this.ownersStatus = 'ready';
    } catch (e) {
      this.ownersError = e instanceof Error ? e.message : String(e);
      this.ownersStatus = 'error';
    }
  }

  /** Owner-name search (case-insensitive substring), ranked by score. */
  searchOwners(term: string, limit = 8): OwnerFilterRecord[] {
    const q = term.trim().toLowerCase();
    if (q.length < 2) return [];
    return this.owners
      .filter((o) => o.owner_name.toLowerCase().includes(q))
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
  }

  updateFilter(patch: Partial<FilterModel>): void {
    this.model = { ...this.model, ...patch };
  }
  reset(): void {
    this.model = emptyFilterModel();
  }
}

function uniqueSorted(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))].sort();
}

export const filterModel = new FilterModelStore();
