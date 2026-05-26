/**
 * Filter execution engine — the seam between filter state and query
 * execution.
 *
 * AppStore previously owned the debounce timer, the concurrency token,
 * the cap on returned ids, and the direct DuckDB calls. That bundled
 * four concerns on a state object: filter state itself, execution
 * mechanics, result storage, and the future scoring step (ADR-058).
 *
 * The engine takes the execution mechanics — debounce + token-based
 * staleness guard + cap — and hides them behind a small interface:
 * `schedule(filters)` / `run(filters)` / `reset()`, with results
 * delivered via a constructor-supplied callback. AppStore mirrors the
 * callback into its `filterCount` / `filterMatchIds` / `filterStatus`
 * reactive fields; everything else (DuckDB, scoring) is one adapter
 * swap away.
 *
 * Two adapters justify the seam today: real DuckDB in the app,
 * deterministic fakes in unit tests. ADR-058's tunable scoring will
 * extend the result shape (`scores?: Map<string, number>`) without
 * touching AppStore.
 */

import type { FilterState } from './filters';
import { composeWhere } from './query';

/** Cap on matching parcel ids returned for the map fade — beyond this
 *  the count badge still shows the true total, but only the top-N by
 *  score are highlighted. */
export const FILTER_FADE_CAP = 20_000;
/** Coalesce a burst of slider / checkbox events into a single query. */
export const FILTER_DEBOUNCE_MS = 160;

export type FilterStatus = 'idle' | 'querying' | 'error';

export interface FilterResult {
  count: number | null;
  matchIds: string[];
  status: FilterStatus;
}

/** What the engine needs from its execution adapter. Two real
 *  implementations today (the live DuckDbEngine + an in-memory test
 *  fake). A future backend filter would be a third adapter, same
 *  interface. */
export interface FilterEngineDeps {
  count: (where: string) => Promise<number>;
  matchingIds: (where: string, limit: number) => Promise<string[]>;
  /** True when the underlying query path is ready (e.g. the slim
   *  parquet is registered). When false the engine short-circuits to
   *  an idle result. */
  available: () => boolean;
}

const IDLE_RESULT: FilterResult = {
  count: null,
  matchIds: [],
  status: 'idle',
};
const QUERYING_RESULT: FilterResult = {
  count: null,
  matchIds: [],
  status: 'querying',
};

/** The engine class. One instance per AppStore. */
export class FilterEngine {
  #deps: FilterEngineDeps;
  #onResult: (r: FilterResult) => void;
  #timer: ReturnType<typeof setTimeout> | null = null;
  /** Monotonic; the result of any run whose token is no longer current
   *  is discarded — a stale slow query never overwrites a newer one. */
  #token = 0;

  constructor(deps: FilterEngineDeps, onResult: (r: FilterResult) => void) {
    this.#deps = deps;
    this.#onResult = onResult;
  }

  /** Debounced run — collapses bursts of filter changes into one query. */
  schedule(filters: FilterState): void {
    if (this.#timer) clearTimeout(this.#timer);
    this.#timer = setTimeout(() => void this.run(filters), FILTER_DEBOUNCE_MS);
  }

  /** Run immediately, bypassing the debounce. Used on boot from a
   *  deep-link and by tests that don't want to await a timer. */
  async run(filters: FilterState): Promise<void> {
    const token = ++this.#token;
    const where = composeWhere(filters);
    if (!where || !this.#deps.available()) {
      this.#emit(token, IDLE_RESULT);
      return;
    }
    this.#emit(token, QUERYING_RESULT);
    try {
      const [count, ids] = await Promise.all([
        this.#deps.count(where),
        this.#deps.matchingIds(where, FILTER_FADE_CAP),
      ]);
      this.#emit(token, { count, matchIds: ids, status: 'idle' });
    } catch {
      this.#emit(token, { count: null, matchIds: [], status: 'error' });
    }
  }

  /** Clear pending work + reset the result to idle. Used on state-switch
   *  so a previous state's stale filter result doesn't bleed through. */
  reset(): void {
    if (this.#timer) {
      clearTimeout(this.#timer);
      this.#timer = null;
    }
    // Bump the token so any in-flight run resolves into a no-op.
    this.#token++;
    this.#onResult(IDLE_RESULT);
  }

  #emit(token: number, result: FilterResult): void {
    if (token !== this.#token) return; // superseded by a newer run / reset
    this.#onResult(result);
  }
}
