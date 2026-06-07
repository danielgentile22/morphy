// Shared Explore tower derivation (UI overhaul #119).
//
// ONE ranked-tower-rows computation drives BOTH the sidebar's live **Towers**
// stat tile and the ranked candidates list, so the number a user reads is the
// number they act on (PRD user stories 5–6, 23). Extracted from ExploreList so
// the tile and the list can never read different counts. The ranking/count
// logic itself is the already-unit-tested `rankedTowerRows`; this module only
// wires the live stores into it.

import { app } from './stores.svelte';
import { filterModel } from './filter-model.svelte';
import { scoring } from './scoring-store.svelte';
import { archivedAntennas } from './archived-antennas.svelte';
import { countMatchingTowers, rankedTowerRows, type TowerListRow } from './tower-list';

class ExploreTowers {
  /** The filtered, archived-aware, de-duplicated, score-ranked tower rows —
   *  narrowed by the SAME shared filter model the map's tower layer uses. */
  rows = $derived<TowerListRow[]>(
    rankedTowerRows(
      app.towerPoints?.features ?? [],
      filterModel.matchingClusterIds,
      (cid) => scoring.scoreOf(cid),
      archivedAntennas.filter,
    ),
  );

  /** How many towers match the active filters — the sidebar Towers tile. Uses
   *  the cheap count-only pass (PERF-007), so reading the tile never forces the
   *  ranked-row sort; that stays reserved for ExploreList, which reads `rows`. */
  count = $derived(
    countMatchingTowers(
      app.towerPoints?.features ?? [],
      filterModel.matchingClusterIds,
      archivedAntennas.filter,
    ),
  );
}

export const exploreTowers = new ExploreTowers();
