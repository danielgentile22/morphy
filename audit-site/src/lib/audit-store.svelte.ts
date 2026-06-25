/**
 * The single reactive data store. Loads `index.json` once at boot and exposes
 * it plus the lookups every view needs (card↔signal indices). Nothing here
 * transforms audit values — it only indexes them — so the UI always reflects
 * the file verbatim (the "never hardcode / auto-populate" contract).
 */

import { fetchIndex, fetchFreshness, fetchFixes, type AuditIndex, type Card, type Signal } from './audit-data';
import type { FreshnessDoc } from './freshness';
import type { FixesDoc } from './fixes';

class AuditStore {
  index = $state<AuditIndex | null>(null);
  loading = $state(true);
  error = $state<string | null>(null);

  // The deploy-time freshness snapshot — `null` until loaded, and stays `null`
  // when the artifact is absent (not yet generated). Loaded alongside the index
  // so both the Overview callout and the "What needs updating" tab read it; its
  // absence never blocks the index load (see fetchFreshness).
  freshness = $state<FreshnessDoc | null>(null);

  // The fix-status board (fixes.json) — `null` until loaded, and stays `null`
  // when the artifact is absent. Loaded alongside the index; its absence never
  // blocks the index load (see fetchFixes).
  fixes = $state<FixesDoc | null>(null);

  cards = $derived<Card[]>(this.index?.cards ?? []);
  signals = $derived<Signal[]>(this.index?.signals ?? []);
  vocab = $derived(this.index?.vocab ?? null);

  cardById = $derived(new Map(this.cards.map((c) => [c.id, c])));
  signalById = $derived(new Map(this.signals.map((s) => [s.id, s])));

  signalsByCard = $derived.by(() => {
    const map = new Map<string, Signal[]>();
    for (const s of this.signals) {
      const list = map.get(s.card);
      if (list) list.push(s);
      else map.set(s.card, [s]);
    }
    return map;
  });

  async load(): Promise<void> {
    this.loading = true;
    this.error = null;
    try {
      // fetchFreshness/fetchFixes never reject (absent artifact → null), so only
      // an index.json failure surfaces as the app-level error state.
      const [index, freshness, fixes] = await Promise.all([
        fetchIndex(),
        fetchFreshness(),
        fetchFixes(),
      ]);
      this.index = index;
      this.freshness = freshness;
      this.fixes = fixes;
    } catch (err) {
      this.error = err instanceof Error ? err.message : String(err);
    } finally {
      this.loading = false;
    }
  }
}

export const store = new AuditStore();
