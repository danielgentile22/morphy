// Archived-antenna state (Svelte 5 runes) — UI overhaul round 2.
//
// An antenna can be *archived* (considered, but not of interest). Archived
// antennas drop out of BOTH Explore lenses — the map's tower layer and the
// ranked tower list — unless the user toggles "show archived". This is
// ASR-grained team state (tenant-scoped on the backend), so it lives here
// rather than in the owner-grained FilterModel; the map + list read its
// `filter` and pass it straight to `filterTowers` / `rankedTowerRows`.

import { fetchArchivedAsrs, updateAntenna } from './leads-api';
import type { ArchivedFilter } from './towers';

class ArchivedAntennasStore {
  /** ASRs the tenant has archived. Hydrated once after sign-in. */
  asrs = $state<Set<string>>(new Set());
  /** Whether archived antennas are currently shown (the filter toggle). */
  show = $state(false);
  status = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');

  /** Load the archived set once (idempotent on success / while loading).
   *  Non-fatal: a failure just leaves the set empty (nothing hidden). */
  async hydrate(): Promise<void> {
    if (this.status === 'loading' || this.status === 'ready') return;
    this.status = 'loading';
    try {
      const r = await fetchArchivedAsrs();
      this.asrs = new Set(r.asrs);
      this.status = 'ready';
    } catch {
      this.status = 'error';
    }
  }

  isArchived(asr: string): boolean {
    return this.asrs.has(asr);
  }

  /** Reflect a local archive change in the set (reassign so runes react). */
  #setLocal(asr: string, archived: boolean): void {
    const next = new Set(this.asrs);
    if (archived) next.add(asr);
    else next.delete(asr);
    this.asrs = next;
  }

  /** Persist an archive/unarchive, then update the shared set so the map +
   *  list re-narrow immediately. */
  async setArchived(asr: string, archived: boolean): Promise<void> {
    await updateAntenna(asr, { archived });
    this.#setLocal(asr, archived);
  }

  setShow(v: boolean): void {
    this.show = v;
  }

  /** The (asrs, show) pair both Explore lenses consume. */
  get filter(): ArchivedFilter {
    return { asrs: this.asrs, show: this.show };
  }
}

export const archivedAntennas = new ArchivedAntennasStore();
