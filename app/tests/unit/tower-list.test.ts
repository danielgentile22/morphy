import { describe, it, expect } from 'vitest';
import { rankedTowerRows, countMatchingTowers } from '../../src/lib/tower-list';
import type { TowerFeature } from '../../src/lib/towers';

function tower(asr: string, cid: string, opts: Partial<TowerFeature['properties']> = {}): TowerFeature {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [0, 0] },
    properties: {
      asr,
      owner: opts.owner ?? `Owner ${cid}`,
      cid,
      height_m: opts.height_m ?? null,
      state: opts.state ?? 'AR',
      active: opts.active ?? true,
    },
  };
}

const SCORES: Record<string, number> = { a: 0.9, b: 0.5, c: 0.7 };
const scoreOf = (cid: string): number | null => SCORES[cid] ?? null;

describe('rankedTowerRows (UI overhaul / #108)', () => {
  it('ranks towers by score descending', () => {
    const rows = rankedTowerRows(
      [tower('T1', 'b'), tower('T2', 'a'), tower('T3', 'c')],
      null,
      scoreOf,
    );
    expect(rows.map((r) => r.asr)).toEqual(['T2', 'T3', 'T1']); // a(.9) c(.7) b(.5)
    expect(rows[0].score).toBe(0.9);
  });

  it('narrows to the shared filter set (matchingClusterIds), null = all', () => {
    const features = [tower('T1', 'a'), tower('T2', 'b'), tower('T3', 'c')];
    expect(rankedTowerRows(features, null, scoreOf)).toHaveLength(3);
    const only = rankedTowerRows(features, new Set(['a', 'c']), scoreOf);
    expect(only.map((r) => r.cid).sort()).toEqual(['a', 'c']);
  });

  it('uses the same narrowing as the map (an empty set keeps nothing)', () => {
    const features = [tower('T1', 'a'), tower('T2', 'b')];
    expect(rankedTowerRows(features, new Set(), scoreOf)).toHaveLength(0);
  });

  it('drops archived towers (by ASR) unless showing archived', () => {
    const features = [tower('T1', 'a'), tower('T2', 'b'), tower('T3', 'c')];
    const hidden = rankedTowerRows(features, null, scoreOf, {
      asrs: new Set(['T2']),
      show: false,
    });
    expect(hidden.map((r) => r.asr)).toEqual(['T1', 'T3']); // T2 archived out
    const shown = rankedTowerRows(features, null, scoreOf, {
      asrs: new Set(['T2']),
      show: true,
    });
    expect(shown.map((r) => r.asr).sort()).toEqual(['T1', 'T2', 'T3']);
  });

  it('sorts unknown-score towers last, tie-breaking by ASR', () => {
    const rows = rankedTowerRows(
      [tower('T9', 'zzz'), tower('T2', 'a'), tower('T1', 'zzz')],
      null,
      scoreOf,
    );
    // a(.9) first; the two unknown-score towers last, ordered by ASR.
    expect(rows.map((r) => r.asr)).toEqual(['T2', 'T1', 'T9']);
    expect(rows[1].score).toBeNull();
  });

  it('de-dups repeated (cid, asr) towers from the source', () => {
    // The tower parquet can carry the same tower twice (ASR matched to
    // overlapping parcels) — the list must show it once (and not collide its key).
    const rows = rankedTowerRows(
      [tower('000400', 'a'), tower('000400', 'a'), tower('T2', 'b')],
      null,
      scoreOf,
    );
    expect(rows).toHaveLength(2);
    expect(rows.filter((r) => r.asr === '000400')).toHaveLength(1);
  });

  it('carries the tower facts + owner link onto each row', () => {
    const rows = rankedTowerRows(
      [tower('T1', 'a', { owner: 'ACME LLC', height_m: 120, state: 'WV', active: false })],
      null,
      scoreOf,
    );
    expect(rows[0]).toMatchObject({
      asr: 'T1',
      owner: 'ACME LLC',
      cid: 'a',
      height_m: 120,
      state: 'WV',
      active: false,
      score: 0.9,
    });
  });
});

describe('countMatchingTowers (PERF-007) matches rankedTowerRows length', () => {
  const archived = { asrs: new Set(['T2']), show: false };
  const cases: Array<[string, TowerFeature[], ReadonlySet<string> | null, typeof archived | undefined]> = [
    ['no filter', [tower('T1', 'a'), tower('T2', 'b'), tower('T3', 'c')], null, undefined],
    ['cluster subset', [tower('T1', 'a'), tower('T2', 'b'), tower('T3', 'c')], new Set(['a', 'c']), undefined],
    ['empty set keeps nothing', [tower('T1', 'a'), tower('T2', 'b')], new Set<string>(), undefined],
    ['archived hidden', [tower('T1', 'a'), tower('T2', 'b'), tower('T3', 'c')], null, archived],
    ['archived shown', [tower('T1', 'a'), tower('T2', 'b')], null, { asrs: new Set(['T2']), show: true }],
    ['dedups repeated (cid,asr)', [tower('000400', 'a'), tower('000400', 'a'), tower('T2', 'b')], null, undefined],
  ];
  it.each(cases)('count == rows.length: %s', (_label, features, matching, arch) => {
    expect(countMatchingTowers(features, matching, arch)).toBe(
      rankedTowerRows(features, matching, scoreOf, arch).length,
    );
  });
});
