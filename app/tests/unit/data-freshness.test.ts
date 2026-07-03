import { describe, it, expect, vi, afterEach } from 'vitest';
import { mount, unmount } from 'svelte';
import { tick } from 'svelte';
import { freshnessRows, fmtDate, type FreshnessDoc } from '../../src/lib/data-freshness';
import DataFreshness from '../../src/components/DataFreshness.svelte';

const NOW = new Date('2026-07-03T12:00:00Z');

const DOC: FreshnessDoc = {
  generated_at: '2026-06-27T05:21:28+00:00',
  sources: [
    // Deliberately out of display order.
    { title: 'parcels-FL', kind: 'fetched', last_pulled: '2026-05-19T15:40:26+00:00' },
    { title: 'fcc-asr', kind: 'fetched', last_pulled: '2026-07-03T08:00:00+00:00' },
    { title: 'owner-clustering', kind: 'derived', last_pulled: null },
    { title: 'billboards-FL', kind: 'fetched', last_pulled: null },
    { title: 'some-new-feed', kind: 'fetched', last_pulled: '2026-07-02T08:00:00+00:00' },
  ],
};

describe('freshnessRows', () => {
  const rows = freshnessRows(DOC, NOW);

  it('keeps fetched sources only, in display order, unmapped titles trailing', () => {
    expect(rows.map((r) => r.label)).toEqual([
      'Cell towers (FCC ASR)',
      'Florida parcels',
      'Florida billboards',
      'some new feed', // unmapped title de-slugged, not dropped
    ]);
  });

  it('formats the refresh date and relative age', () => {
    const fl = rows.find((r) => r.label === 'Florida parcels')!;
    expect(fl.refreshed).toBe('May 19, 2026');
    expect(fl.ago).toBe('44 days ago'); // floored whole days (pull 15:40 UTC vs now 12:00 UTC)
    const asr = rows.find((r) => r.label === 'Cell towers (FCC ASR)')!;
    expect(asr.ago).toBe('today');
  });

  it('renders never-pulled sources without a fabricated date', () => {
    const bb = rows.find((r) => r.label === 'Florida billboards')!;
    expect(bb.refreshed).toBeNull();
    expect(bb.ago).toBe('never pulled');
  });
});

describe('fmtDate', () => {
  it('formats in UTC and tolerates junk', () => {
    expect(fmtDate('2026-06-27T05:21:28+00:00')).toBe('Jun 27, 2026');
    expect(fmtDate(null)).toBeNull();
    expect(fmtDate('not-a-date')).toBeNull();
  });
});

// Component wiring — the real component in jsdom via Svelte 5 `mount`
// (repo pattern; see carrier-list.test.ts), with `fetch` stubbed.
describe('DataFreshness component', () => {
  let target: HTMLElement;
  let app: Record<string, unknown> | null = null;

  async function render(): Promise<HTMLElement> {
    target = document.createElement('div');
    document.body.appendChild(target);
    app = mount(DataFreshness, { target });
    // onMount fetch → two microtask hops (json + state), then a render tick.
    await new Promise((r) => setTimeout(r, 0));
    await tick();
    return target;
  }

  afterEach(() => {
    if (app) unmount(app);
    app = null;
    target?.remove();
    vi.unstubAllGlobals();
  });

  it('renders a row per fetched source from the snapshot', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(DOC) }),
    );
    const el = await render();
    const table = el.querySelector('[data-testid="freshness-table"]')!;
    expect(table).toBeTruthy();
    expect(table.querySelectorAll('tr')).toHaveLength(4); // derived excluded
    expect(table.textContent).toContain('Florida parcels');
    expect(el.textContent).toContain('Snapshot from the last deploy');
  });

  it('degrades to a quiet placeholder when the snapshot is missing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    const el = await render();
    expect(el.querySelector('[data-testid="freshness-unavailable"]')).toBeTruthy();
  });
});
