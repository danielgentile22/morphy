// Client loader for the slim cross-state owners filter index
// (`composite/owners_filter.json`, schema v3 / Slice 6 #52).
//
// The full owners index (holdings + mailing) is tens of MB and lives only on
// the backend; this slim companion carries just the filter + search fields the
// shared FilterModel needs. Loaded once, it powers BOTH the map's tower
// narrowing (owner-id set ∈ filter) and the owner-name search — the same static
// read-layer path as the rest of the app's `/data/...` assets.

import type { FilterableOwner } from './filter-model';

/** One owner in the slim filter index — `FilterableOwner` plus identity. */
export interface OwnerFilterRecord extends FilterableOwner {
  display_cluster_id: string;
  owner_name: string;
  n_states: number;
  cross_state: boolean;
}

const OWNERS_FILTER_URL = '/data/processed/composite/owners_filter.json';

function strList(v: unknown): string[] {
  return Array.isArray(v) ? v.map(String) : [];
}
function num(v: unknown, fallback = 0): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

/** Coerce one raw JSON owner into a typed record (tolerant of a stale/partial
 *  index — missing filter fields degrade to "no constraint" values). */
function toRecord(o: Record<string, unknown>): OwnerFilterRecord {
  return {
    display_cluster_id: String(o.display_cluster_id ?? ''),
    owner_name: String(o.owner_name ?? ''),
    owner_kind: String(o.owner_kind ?? ''),
    states: strList(o.states),
    n_states: num(o.n_states),
    cross_state: o.cross_state === true,
    counties: strList(o.counties),
    distress_tier: String(o.distress_tier ?? ''),
    in_oz: o.in_oz === true,
    in_qct: o.in_qct === true,
    persistent_poverty: o.persistent_poverty === true,
    score: num(o.score),
    parcel_count: num(o.parcel_count),
    tower_count: num(o.tower_count),
    solar_count: num(o.solar_count),
    structure_count: num(o.structure_count),
    structure_types: strList(o.structure_types),
    active_tower_count: num(o.active_tower_count),
    total_assessed_value: num(o.total_assessed_value),
    tallest_tower_height_m:
      o.tallest_tower_height_m == null ? null : num(o.tallest_tower_height_m, 0),
  };
}

/** Fetch + parse the slim owners filter index. Throws an actionable error if
 *  the static data server isn't reachable (same posture as `data.ts`). */
export async function loadOwnersFilterIndex(): Promise<OwnerFilterRecord[]> {
  let res: Response;
  try {
    res = await fetch(OWNERS_FILTER_URL);
  } catch (e) {
    throw new Error(
      `Could not reach ${OWNERS_FILTER_URL}. Is the data server running ` +
        `(python scripts/serve.py 8765)? Run \`python scripts/preprocess.py --owners-index\` ` +
        `to build it. — ${String(e)}`,
    );
  }
  if (!res.ok) throw new Error(`${OWNERS_FILTER_URL} — HTTP ${res.status} ${res.statusText}`);
  const json = (await res.json()) as { owners?: unknown };
  const owners = Array.isArray(json.owners) ? json.owners : [];
  return owners
    .filter((o): o is Record<string, unknown> => typeof o === 'object' && o !== null)
    .map(toRecord);
}
