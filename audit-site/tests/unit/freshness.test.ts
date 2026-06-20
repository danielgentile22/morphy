import { describe, it, expect } from 'vitest';
import {
  computeFreshness,
  daysSince,
  freshnessRows,
  freshnessSummary,
  statusBadge,
  cadenceLabel,
  relativeDays,
  DUE_SOON_FRACTION,
  type FreshnessSource,
  type FreshnessDoc,
} from '../../src/lib/freshness';

// Pinned "now" mirrors test_export_freshness.NOW so the client model and the
// Python exporter assert the same thresholds against the same fixtures.
const NOW = new Date('2026-06-20T00:00:00Z');
const DAY = 86_400_000;

/** A fetched source pulled `daysAgo` before NOW with the given cadence, built
 *  exactly as the exporter writes it: `next_check = last_pulled + cadence`.
 *  `cadence = null` ⇒ no declared schedule (and no next_check). */
function src(daysAgo: number, cadence: number | null, over: Partial<FreshnessSource> = {}): FreshnessSource {
  const pulled = new Date(NOW.getTime() - daysAgo * DAY);
  return {
    id: 'T-01',
    title: 'fcc-asr',
    kind: 'fetched',
    manifest_source_ids: ['fcc_asr'],
    last_pulled: pulled.toISOString(),
    cadence_days: cadence,
    next_check: cadence === null ? null : new Date(pulled.getTime() + cadence * DAY).toISOString(),
    status: 'fresh',
    rebuilt_not_fetched: false,
    ...over,
  };
}

function derived(over: Partial<FreshnessSource> = {}): FreshnessSource {
  return {
    id: 'T-08',
    title: 'owner-clustering',
    kind: 'derived',
    manifest_source_ids: [],
    last_pulled: null,
    cadence_days: null,
    next_check: null,
    status: 'rebuilt',
    rebuilt_not_fetched: true,
    ...over,
  };
}

describe('computeFreshness — status mirrors the manifest thresholds', () => {
  it('is fresh just after a pull (well within the window)', () => {
    expect(computeFreshness(src(1, 7), NOW).status).toBe('fresh');
  });

  it('is due_soon past 50% of the cadence window', () => {
    // 5 of 7 days elapsed → past the 3.5-day half-window → due soon.
    expect(computeFreshness(src(5, 7), NOW).status).toBe('due_soon');
  });

  it('is stale past the next recommended check', () => {
    expect(computeFreshness(src(10, 7), NOW).status).toBe('stale');
  });

  it('treats the exact next-check boundary as stale (>=, mirrors the puller)', () => {
    // pulled exactly `cadence` days ago → now === next_check → stale.
    expect(computeFreshness(src(7, 7), NOW).status).toBe('stale');
  });

  it('treats the exact due-soon boundary as due_soon', () => {
    // half-window is the boundary; DUE_SOON_FRACTION pins it at 0.5.
    expect(DUE_SOON_FRACTION).toBe(0.5);
    expect(computeFreshness(src(5, 10), NOW).status).toBe('due_soon'); // 5 of 10 = exactly half
    expect(computeFreshness(src(4, 10), NOW).status).toBe('fresh'); // just under half
  });

  it('is unknown with no declared cadence (no fabricated due-date)', () => {
    const v = computeFreshness(src(400, null), NOW);
    expect(v.status).toBe('unknown');
    // …but the pull is still dated honestly — we pulled it, just can't judge staleness.
    expect(v.daysAgo).toBe(400);
  });

  it('is unknown when never pulled', () => {
    const v = computeFreshness(src(0, null, { last_pulled: null }), NOW);
    expect(v.status).toBe('unknown');
    expect(v.daysAgo).toBeNull();
  });

  it('short-circuits derived sources to rebuilt with no age', () => {
    const v = computeFreshness(derived(), NOW);
    expect(v.status).toBe('rebuilt');
    expect(v.daysAgo).toBeNull();
  });
});

describe('daysSince', () => {
  it('floors to whole days and never goes negative', () => {
    expect(daysSince(src(3, 7).last_pulled, NOW)).toBe(3);
    expect(daysSince(new Date(NOW.getTime() + 5 * DAY).toISOString(), NOW)).toBe(0); // future → 0
    expect(daysSince(null, NOW)).toBeNull();
  });
});

describe('freshnessRows — worst-first ordering + live projection', () => {
  const doc: FreshnessDoc = {
    schema_version: 1,
    generated_at: NOW.toISOString(),
    manifest: { present: true, last_full_check: null },
    note: '',
    sources: [
      src(1, 7, { id: 'T-04', title: 'fresh-one' }), // fresh
      src(10, 7, { id: 'T-01', title: 'overdue-one' }), // stale
      src(5, 7, { id: 'T-02', title: 'soon-one' }), // due_soon
      derived({ id: 'T-08' }), // rebuilt
      src(0, null, { id: 'T-13', title: 'no-cadence', last_pulled: null }), // unknown
    ],
  };

  it('orders stale → due_soon → fresh → unknown → rebuilt', () => {
    const order = freshnessRows(doc, NOW).map((r) => r.verdict.status);
    expect(order).toEqual(['stale', 'due_soon', 'fresh', 'unknown', 'rebuilt']);
  });

  it('recomputes status live rather than echoing the baked value', () => {
    // Baked status says "fresh" on every fixture; the live model must override it.
    const stale = freshnessRows(doc, NOW).find((r) => r.source.id === 'T-01');
    expect(stale?.source.status).toBe('fresh'); // baked
    expect(stale?.verdict.status).toBe('stale'); // live
  });
});

describe('freshnessSummary', () => {
  it('counts every status and buckets stale + due-soon', () => {
    const rows = freshnessRows(
      {
        schema_version: 1,
        generated_at: NOW.toISOString(),
        manifest: { present: true, last_full_check: null },
        note: '',
        sources: [
          src(10, 7, { id: 'T-01' }),
          src(11, 7, { id: 'T-02' }),
          src(5, 7, { id: 'T-03' }),
          src(1, 7, { id: 'T-04' }),
          derived({ id: 'T-08' }),
        ],
      },
      NOW,
    );
    const s = freshnessSummary(rows);
    expect(s.counts).toEqual({ stale: 2, due_soon: 1, fresh: 1, unknown: 0, rebuilt: 1 });
    expect(s.stale.map((r) => r.source.id)).toEqual(['T-01', 'T-02']);
    expect(s.dueSoon.map((r) => r.source.id)).toEqual(['T-03']);
  });
});

describe('presentation helpers', () => {
  it('maps status → badge label + tone', () => {
    expect(statusBadge('stale')).toEqual({ label: 'Overdue', tone: 'bad' });
    expect(statusBadge('due_soon')).toEqual({ label: 'Due soon', tone: 'warn' });
    expect(statusBadge('fresh')).toEqual({ label: 'Fresh', tone: 'good' });
    expect(statusBadge('rebuilt').tone).toBe('muted');
    expect(statusBadge('unknown').tone).toBe('muted');
  });

  it('humanises common cadences and falls back to "every N days"', () => {
    expect(cadenceLabel(7)).toBe('Weekly');
    expect(cadenceLabel(365)).toBe('Yearly');
    expect(cadenceLabel(45)).toBe('Every 45 days');
    expect(cadenceLabel(null)).toBe('—');
  });

  it('renders relative pull ages', () => {
    expect(relativeDays(0)).toBe('today');
    expect(relativeDays(1)).toBe('yesterday');
    expect(relativeDays(9)).toBe('9 days ago');
    expect(relativeDays(null)).toBe('never pulled');
  });
});
