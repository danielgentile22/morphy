import { describe, it, expect, vi, afterEach } from 'vitest';
import { prefetchMapData, onIdle, type IdleScheduler } from '../../src/lib/boot-prefetch';
import { AppStore } from '../../src/lib/stores.svelte';
import { filterModel } from '../../src/lib/filter-model.svelte';

// Idle-gated boot prefetch (#168 / PRD #163 M3). We assert *observable* wiring
// only: that the warm is gated behind the idle scheduler, that both loads fire,
// that a failing warm never aborts the other or rejects into the Dashboard, and
// — against the real stores — that warming then re-triggering (the Explore-route
// `bootMap()` / `FilterPanel.onMount` load) loads each asset exactly once. The
// idempotency lives in the stores' own latches; this proves the seam uses them.

/** An idle scheduler that runs the callback synchronously — "the page is idle
 *  now". Lets a test observe the scheduled warm without a timer. */
const runNow: IdleScheduler = (cb) => cb();

afterEach(() => vi.unstubAllGlobals());

describe('prefetchMapData wiring', () => {
  it('warms both the map boot and the owners index once the page is idle', () => {
    const bootMap = vi.fn();
    const loadOwners = vi.fn();
    prefetchMapData({ bootMap, loadOwners, idle: runNow });
    expect(bootMap).toHaveBeenCalledTimes(1);
    expect(loadOwners).toHaveBeenCalledTimes(1);
  });

  it('is idle-gated — neither warm runs until the idle callback fires', () => {
    let fire: (() => void) | null = null;
    const capture: IdleScheduler = (cb) => {
      fire = cb;
    };
    const bootMap = vi.fn();
    const loadOwners = vi.fn();

    prefetchMapData({ bootMap, loadOwners, idle: capture });
    // Scheduled, but the Dashboard-critical fetches get the network first.
    expect(bootMap).not.toHaveBeenCalled();
    expect(loadOwners).not.toHaveBeenCalled();

    fire!();
    expect(bootMap).toHaveBeenCalledTimes(1);
    expect(loadOwners).toHaveBeenCalledTimes(1);
  });

  it('swallows a rejecting warm — the other still runs and nothing rejects', async () => {
    const bootMap = vi.fn(() => Promise.reject(new Error('tower fetch failed')));
    const loadOwners = vi.fn(() => Promise.resolve());

    expect(() => prefetchMapData({ bootMap, loadOwners, idle: runNow })).not.toThrow();
    expect(loadOwners).toHaveBeenCalledTimes(1);
    // Let the rejected warm settle; the swallow's .catch keeps it unhandled-free.
    await Promise.resolve();
  });

  it('swallows a synchronously-throwing warm without skipping the other', () => {
    const bootMap = vi.fn(() => {
      throw new Error('sync boom');
    });
    const loadOwners = vi.fn();

    expect(() => prefetchMapData({ bootMap, loadOwners, idle: runNow })).not.toThrow();
    // The two warms are isolated — a sync throw in one never blocks the other.
    expect(loadOwners).toHaveBeenCalledTimes(1);
  });
});

describe('onIdle scheduler', () => {
  it('defers to requestIdleCallback when available (with a timeout)', () => {
    let wrapped: (() => void) | null = null;
    const ric = vi.fn((cb: () => void, _opts?: { timeout: number }) => {
      wrapped = cb;
      return 1;
    });
    vi.stubGlobal('requestIdleCallback', ric);

    const cb = vi.fn();
    onIdle(cb);
    expect(ric).toHaveBeenCalledTimes(1);
    // A busy tab still warms eventually — the timeout is passed through.
    expect(ric.mock.calls[0][1]).toEqual({ timeout: 2000 });
    expect(cb).not.toHaveBeenCalled();

    wrapped!();
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it('falls back to a macrotask when requestIdleCallback is absent', () => {
    // jsdom has no requestIdleCallback; assert the fallback path explicitly.
    vi.stubGlobal('requestIdleCallback', undefined);
    vi.useFakeTimers();
    try {
      const cb = vi.fn();
      onIdle(cb);
      expect(cb).not.toHaveBeenCalled();
      vi.runAllTimers();
      expect(cb).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});

// ── idempotency against the real stores ────────────────────────────────────
// The prefetch warms the same store loaders the Explore route / FilterPanel
// mount call. Proven here: a second call (the route trigger) issues zero new
// network requests — the guard already loaded the asset.

interface FakeResponse {
  ok: boolean;
  status: number;
  statusText?: string;
  json?: () => Promise<unknown>;
}

/** A `fetch` stub routed by URL fragment. HEAD probes resolve "present"; GETs
 *  return the matching body. Records calls so a test can count loads per URL. */
function routedFetch(routes: [string, unknown][]) {
  return vi.fn((input: string, init?: { method?: string }): Promise<FakeResponse> => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    if (method === 'HEAD') return Promise.resolve({ ok: true, status: 200 });
    for (const [frag, body] of routes) {
      if (url.includes(frag)) {
        return Promise.resolve({ ok: true, status: 200, json: async () => body });
      }
    }
    return Promise.resolve({ ok: false, status: 404, statusText: 'Not Found' });
  });
}

/** Count the GET (non-HEAD) requests whose URL contains `frag`. */
function getCount(spy: ReturnType<typeof routedFetch>, frag: string): number {
  return spy.mock.calls.filter(
    ([url, init]) => (init?.method ?? 'GET') !== 'HEAD' && String(url).includes(frag),
  ).length;
}

const INDEX_JSON = {
  schema_version: 1,
  generated_at: '',
  states: [
    { fips: '05', abbr: 'AR', name: 'Arkansas', bbox: [-94.6, 33, -89.6, 36.5], counts: {} },
  ],
};

const TOWERS_JSON = {
  schema_version: 1,
  towers: [
    { asr: '1001', owner: 'Owner A', height_m: 50, state: '05', active: true, lat: 34.5, lon: -92.3 },
  ],
};

const OWNERS_JSON = {
  owners: [{ display_cluster_id: 'c1', owner_name: 'Owner A', score: 9, parcel_count: 2 }],
};

describe('idempotent warm against the real stores', () => {
  it('bootMap: warming then the Explore-route re-trigger loads towers + index once', async () => {
    const fetchSpy = routedFetch([
      ['index.json', INDEX_JSON],
      ['towers.json', TOWERS_JSON],
    ]);
    vi.stubGlobal('fetch', fetchSpy);
    const app = new AppStore();

    await app.bootMap(); // the prefetch warm
    await vi.waitFor(() => expect(app.towersStatus).toBe('ready'));
    expect(getCount(fetchSpy, 'towers.json')).toBe(1);
    expect(getCount(fetchSpy, 'index.json')).toBe(1);
    expect(app.towerPoints?.features).toHaveLength(1);

    await app.bootMap(); // the Explore-route trigger → no-op via mapBooted
    await Promise.resolve();
    expect(getCount(fetchSpy, 'towers.json')).toBe(1);
    expect(getCount(fetchSpy, 'index.json')).toBe(1);
  });

  it('owners index: warming then the FilterPanel.onMount re-load fetches it once', async () => {
    const fetchSpy = routedFetch([['owners_filter.json', OWNERS_JSON]]);
    vi.stubGlobal('fetch', fetchSpy);

    await filterModel.load(); // the prefetch warm
    expect(filterModel.ownersStatus).toBe('ready');
    expect(filterModel.owners).toHaveLength(1);

    await filterModel.load(); // FilterPanel.onMount → no-op via ownersStatus
    expect(getCount(fetchSpy, 'owners_filter.json')).toBe(1);
  });
});
