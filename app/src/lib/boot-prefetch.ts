// Idle-gated boot prefetch — warm the heavy Explore map + owners-filter index
// DURING the Dashboard so opening Explore is instant (#168 / PRD #163 M3).
//
// Right after the session verifies (App.svelte), this kicks off the two heavy
// loads the user would otherwise wait on at the Explore route: the national
// tower layer + parcel-tile probes (`AppStore.bootMap`, now the fast
// `towers.json` path from #166) and the slim owners filter index
// (`FilterModelStore.load`). Both fire behind an idle gate so the
// Dashboard-critical fetches (nav counts, attention badge, user settings) claim
// the network first; by the time Explore opens, the tower + owners data is
// already in flight or done — ≈ 0 ms of added wait in the common path.
//
// No new state machine: idempotency is delegated entirely to the stores' own
// latches — `AppStore.mapBooted` and `FilterModelStore.ownersStatus`. So the
// existing Explore-route `bootMap()` trigger and `FilterPanel.onMount` load
// both become no-ops once the prefetch has run; nothing double-loads. And the
// warm is fire-and-forget: a failed or aborted load can never reject into the
// Dashboard, and a session that never opens the map simply leaves the warmed
// data sitting unused in the stores.

import { app } from './stores.svelte';
import { filterModel } from './filter-model.svelte';

/** Schedules a callback to run when the page is idle. */
export type IdleScheduler = (cb: () => void) => void;

interface RequestIdleCapable {
  requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
}

/**
 * Run `cb` once the browser is idle — after the Dashboard's synchronous boot
 * work and its critical fetches have had first claim on the main thread.
 * Prefers `requestIdleCallback` (with a `timeout` so a busy tab still warms
 * eventually); falls back to a macrotask where it is unavailable (older Safari,
 * and the jsdom test env). Best-effort by contract — must never throw into the
 * caller.
 */
export function onIdle(cb: () => void, timeout = 2000): void {
  const ric = (globalThis as RequestIdleCapable).requestIdleCallback;
  if (typeof ric === 'function') {
    ric(() => cb(), { timeout });
    return;
  }
  setTimeout(cb, 0);
}

/** Run a warm, swallowing both a synchronous throw and an async rejection — so
 *  one failing load never aborts the other, and neither can reject into the
 *  Dashboard (a failed/aborted prefetch must never break it). The stores
 *  already record their own error status; this is the last-line guarantee. */
function swallow(warm: () => Promise<void> | void): void {
  try {
    const r = warm();
    if (r && typeof (r as Promise<void>).then === 'function') {
      (r as Promise<void>).catch(() => {});
    }
  } catch {
    /* synchronous throw — swallowed; the Dashboard is unaffected. */
  }
}

/** Injectable seams: the defaults wire the real singletons + idle scheduler;
 *  tests pass spies plus a synchronous/capturing idle to assert the wiring. */
export interface PrefetchDeps {
  bootMap: () => Promise<void> | void;
  loadOwners: () => Promise<void> | void;
  idle: IdleScheduler;
}

const defaultDeps: PrefetchDeps = {
  bootMap: () => app.bootMap(),
  loadOwners: () => filterModel.load(),
  idle: onIdle,
};

/**
 * Schedule the idle-gated warm of the heavy map stack + owners filter index.
 * Idempotency is delegated to the stores' guards, so calling this AND later
 * opening Explore / mounting the FilterPanel still loads each asset exactly
 * once. Fire-and-forget: returns immediately, never rejects.
 */
export function prefetchMapData(deps: Partial<PrefetchDeps> = {}): void {
  const { bootMap, loadOwners, idle } = { ...defaultDeps, ...deps };
  idle(() => {
    swallow(bootMap);
    swallow(loadOwners);
  });
}
