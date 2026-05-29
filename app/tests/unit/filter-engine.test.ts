import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  FILTER_FADE_CAP,
  FilterEngine,
  type FilterResult,
  type FilterEngineDeps,
} from '../../src/lib/filter-engine';
import { emptyFilters, type FilterState } from '../../src/lib/filters';

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

function activeFilters(): FilterState {
  return { ...emptyFilters(), hasTower: true };
}

function fakeDeps(overrides: Partial<FilterEngineDeps> = {}): FilterEngineDeps {
  return {
    count: async () => 0,
    matchingIds: async () => [],
    available: () => true,
    ...overrides,
  };
}

describe('FilterEngine.run', () => {
  it('emits idle when no filter is active', async () => {
    const results: FilterResult[] = [];
    const engine = new FilterEngine(fakeDeps(), (r) => results.push(r));
    await engine.run(emptyFilters());
    expect(results.at(-1)).toEqual({ count: null, matchIds: [], status: 'idle' });
  });

  it('emits querying then idle with count + ids when active', async () => {
    const results: FilterResult[] = [];
    const engine = new FilterEngine(
      fakeDeps({
        count: async () => 42,
        matchingIds: async () => ['a', 'b'],
      }),
      (r) => results.push(r),
    );
    await engine.run(activeFilters());
    expect(results.map((r) => r.status)).toEqual(['querying', 'idle']);
    expect(results.at(-1)).toEqual({ count: 42, matchIds: ['a', 'b'], status: 'idle' });
  });

  it('emits error on failure', async () => {
    const results: FilterResult[] = [];
    const engine = new FilterEngine(
      fakeDeps({
        count: async () => {
          throw new Error('boom');
        },
      }),
      (r) => results.push(r),
    );
    await engine.run(activeFilters());
    expect(results.at(-1)?.status).toBe('error');
  });

  it('short-circuits when available() is false', async () => {
    const counted = vi.fn(async () => 1);
    const results: FilterResult[] = [];
    const engine = new FilterEngine(
      fakeDeps({ available: () => false, count: counted }),
      (r) => results.push(r),
    );
    await engine.run(activeFilters());
    expect(counted).not.toHaveBeenCalled();
    expect(results.at(-1)?.status).toBe('idle');
  });

  it('passes FILTER_FADE_CAP to matchingIds', async () => {
    const matchingIds = vi.fn(async () => [] as string[]);
    const engine = new FilterEngine(fakeDeps({ matchingIds }), () => undefined);
    await engine.run(activeFilters());
    expect(matchingIds).toHaveBeenCalledWith(expect.any(String), FILTER_FADE_CAP);
  });
});

describe('FilterEngine staleness', () => {
  it('discards a slow stale run when a fresh run takes over', async () => {
    let resolveSlow!: (n: number) => void;
    const slowCount = new Promise<number>((res) => {
      resolveSlow = res;
    });

    let call = 0;
    const results: FilterResult[] = [];
    const engine = new FilterEngine(
      fakeDeps({
        count: async () => {
          call += 1;
          if (call === 1) return slowCount;
          return 99;
        },
        matchingIds: async () => [],
      }),
      (r) => results.push(r),
    );

    // Kick off the slow run; do not await it.
    const slow = engine.run(activeFilters());
    // Immediately fire a second, fresh run (different filter shape).
    await engine.run({ ...activeFilters(), hasSolar: true });
    // Now let the slow one resolve — its result must NOT overwrite.
    resolveSlow(11);
    await slow;

    const final = results.at(-1)!;
    expect(final.status).toBe('idle');
    expect(final.count).toBe(99); // from the fresh run, not 11
  });
});

describe('FilterEngine.schedule (debounce)', () => {
  it('coalesces a burst into a single query', async () => {
    const counted = vi.fn(async () => 7);
    const engine = new FilterEngine(fakeDeps({ count: counted }), () => undefined);
    engine.schedule(activeFilters());
    engine.schedule(activeFilters());
    engine.schedule(activeFilters());
    // Before the debounce expires nothing has fired.
    expect(counted).not.toHaveBeenCalled();
    // Advance past the debounce window.
    await vi.advanceTimersByTimeAsync(200);
    expect(counted).toHaveBeenCalledTimes(1);
  });
});

describe('FilterEngine.reset', () => {
  it('emits idle and discards a pending scheduled run', async () => {
    const counted = vi.fn(async () => 5);
    const results: FilterResult[] = [];
    const engine = new FilterEngine(fakeDeps({ count: counted }), (r) =>
      results.push(r),
    );
    engine.schedule(activeFilters());
    engine.reset();
    await vi.advanceTimersByTimeAsync(500);
    expect(counted).not.toHaveBeenCalled();
    expect(results.at(-1)).toEqual({ count: null, matchIds: [], status: 'idle' });
  });
});
