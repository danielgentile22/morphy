// Client loader for the slim cross-state owners filter index
// (`composite/owners_filter.json`, schema v3 / Slice 6 #52).
//
// The full owners index (holdings + mailing) is tens of MB and lives only on
// the backend; this slim companion carries just the filter + search fields the
// shared FilterModel needs. Loaded once, it powers BOTH the map's tower
// narrowing (owner-id set ∈ filter) and the owner-name search — the same static
// read-layer path as the rest of the app's `/data/...` assets.

import { coerceNum, coerceOwnerFeatures, type OwnerFeatures } from './owner-features';

/** One owner in the slim filter index — the shared `OwnerFeatures` plus the
 *  index's own identity fields. */
export interface OwnerFilterRecord extends OwnerFeatures {
  display_cluster_id: string;
  owner_name: string;
  n_states: number;
  cross_state: boolean;
}

const OWNERS_FILTER_URL = '/data/processed/composite/owners_filter.json';

/** Coerce one raw JSON owner into a typed record: the shared feature columns
 *  (via `coerceOwnerFeatures`) plus this index's identity fields. */
function toRecord(o: Record<string, unknown>): OwnerFilterRecord {
  return {
    ...coerceOwnerFeatures(o),
    display_cluster_id: String(o.display_cluster_id ?? ''),
    owner_name: String(o.owner_name ?? ''),
    n_states: coerceNum(o.n_states),
    cross_state: o.cross_state === true,
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
