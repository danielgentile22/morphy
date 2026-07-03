import { describe, it, expect, vi, afterEach } from 'vitest';
import type { TowerRow } from '../../src/lib/duckdb';
import { ownerNameToClusterId } from '../../src/lib/owner-cluster';

// The national-towers loader (PRD #163 / #166) takes DuckDB-WASM off the tower
// critical path: it fetches the precomputed `composite/towers.json` and maps it
// through the same pure `rowsToFeatureCollection`. We assert observable
// behavior only — the resulting FeatureCollection for a present file, and the
// fall-back to the per-state DuckDB union when the file is absent/malformed —
// by stubbing `fetch` (mirroring store-load-dedupe.test.ts) and the lowest
// DuckDB seam (`duckDb.loadTowerPoints`). Never reach into private state.

// Stub the DuckDB engine so the fallback path is observable without booting
// WASM. The present-file path never touches it (the whole point of this slice).
const { duckLoadTowerPoints } = vi.hoisted(() => ({ duckLoadTowerPoints: vi.fn() }));
vi.mock('../../src/lib/duckdb', () => ({
  duckDb: { loadTowerPoints: duckLoadTowerPoints },
}));

import { loadNationalTowers, parseNationalTowers } from '../../src/lib/towers';

/** A `fetch` stub answering HEAD probes and GET bodies independently, keyed by
 *  URL so towers.json can be made present/absent separately from the parquet. */
function stubFetch(opts: {
  head: (url: string) => boolean;
  json?: (url: string) => unknown;
}): void {
  const spy = vi.fn((url: string, init?: { method?: string }) => {
    if (init?.method === 'HEAD') {
      return Promise.resolve({ ok: opts.head(url) } as unknown as Response);
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => (opts.json ? opts.json(url) : {}),
    } as unknown as Response);
  });
  vi.stubGlobal('fetch', spy);
}

const AR_FILE = {
  schema_version: 1,
  towers: [
    {
      asr: '080946',
      owner: 'MITCHELL VICKI',
      cid: ownerNameToClusterId('MITCHELL VICKI'),
      height_m: 79.248,
      state: 'AR',
      active: true,
      lat: 33.0,
      lon: -91.3,
    },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
  duckLoadTowerPoints.mockReset();
});

describe('parseNationalTowers', () => {
  it('maps rows to TowerRow, defaulting missing keys (stale-file safe)', () => {
    const rows = parseNationalTowers({
      schema_version: 1,
      towers: [
        { asr: '080946', owner: 'MITCHELL VICKI', cid: 'baked0000001', height_m: 79.248, state: 'AR', active: true, lat: 33, lon: -91.3 },
        { asr: '080947', state: 'AR', lat: 34, lon: -92 }, // no owner / cid / height / active
      ],
    });
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({
      asr: '080946',
      owner: 'MITCHELL VICKI',
      cid: 'baked0000001', // baked Lead key passed through
      height_m: 79.248,
      state: 'AR',
      active: true,
      lat: 33,
      lon: -91.3,
      // v1-file rows have no v2 fields → safe null defaults (stale-file safe).
      date_built: null,
      tower_owner: null,
      tower_owner_street: null,
      tower_owner_city: null,
      tower_owner_state: null,
      tower_owner_zip: null,
      tower_owner_phone: null,
    });
    expect(rows[1].owner).toBeNull();
    expect(rows[1].cid).toBeUndefined(); // absent → recomputed downstream
    expect(rows[1].height_m).toBeNull();
    expect(rows[1].active).toBeNull();
  });

  it('passes the v2 build-date + tower-owner contact fields through (M-b/M-c)', () => {
    const rows = parseNationalTowers({
      schema_version: 2,
      towers: [
        {
          asr: '080946', owner: 'MITCHELL VICKI', state: 'AR', lat: 33, lon: -91.3,
          date_built: '1990-06-14', tower_owner: 'SBA TOWERS II LLC',
          tower_owner_street: '8051 CONGRESS AVE', tower_owner_city: 'BOCA RATON',
          tower_owner_state: 'FL', tower_owner_zip: '33487', tower_owner_phone: '(561) 995-7670',
        },
      ],
    });
    expect(rows[0].date_built).toBe('1990-06-14');
    expect(rows[0].tower_owner).toBe('SBA TOWERS II LLC');
    expect(rows[0].tower_owner_zip).toBe('33487');
    expect(rows[0].tower_owner_phone).toBe('(561) 995-7670');
  });

  it('throws when the envelope has no towers[] array (loader then falls back)', () => {
    expect(() => parseNationalTowers({})).toThrow();
    expect(() => parseNationalTowers(null)).toThrow();
    expect(() => parseNationalTowers({ towers: 'nope' })).toThrow();
  });
});

describe('loadNationalTowers', () => {
  it('present file → FeatureCollection via rowsToFeatureCollection, DuckDB untouched', async () => {
    stubFetch({ head: () => true, json: () => AR_FILE });

    const fc = await loadNationalTowers(['05', '12']);
    expect(fc.type).toBe('FeatureCollection');
    expect(fc.features).toHaveLength(1);
    const f = fc.features[0];
    expect(f.geometry).toEqual({ type: 'Point', coordinates: [-91.3, 33.0] });
    expect(f.properties.owner).toBe('MITCHELL VICKI');
    // cid is derived client-side from the owner name (single source of truth).
    expect(f.properties.cid).toBe(ownerNameToClusterId('MITCHELL VICKI'));
    expect(duckLoadTowerPoints).not.toHaveBeenCalled();
  });

  it('prefers a baked cid over recomputing, and recomputes when absent', async () => {
    // A sentinel cid that differs from the recipe proves the baked value wins;
    // a row with no cid proves the client still derives it (stale-file safe).
    stubFetch({
      head: () => true,
      json: () => ({
        schema_version: 1,
        towers: [
          { asr: 'a', owner: 'MITCHELL VICKI', cid: 'sentinelcid0', state: 'AR', lat: 33, lon: -91 },
          { asr: 'b', owner: 'MITCHELL VICKI', state: 'AR', lat: 34, lon: -92 }, // no cid
        ],
      }),
    });

    const fc = await loadNationalTowers(['05']);
    const byAsr = Object.fromEntries(fc.features.map((f) => [f.properties.asr, f.properties.cid]));
    expect(byAsr.a).toBe('sentinelcid0'); // baked value preferred
    expect(byAsr.b).toBe(ownerNameToClusterId('MITCHELL VICKI')); // recomputed
    expect(duckLoadTowerPoints).not.toHaveBeenCalled();
  });

  it('absent file → falls back to the per-state DuckDB union (towers still render)', async () => {
    // towers.json 404s; the per-state towers.parquet probes present → DuckDB.
    stubFetch({ head: (url) => !url.endsWith('towers.json') });
    const fallbackRows: TowerRow[] = [
      { asr: 'fb', owner: 'WEYERHAEUSER COMPANY', height_m: null, state: 'AR', active: true, lat: 30, lon: -90 },
    ];
    duckLoadTowerPoints.mockResolvedValue(fallbackRows);

    const fc = await loadNationalTowers(['05']);
    expect(duckLoadTowerPoints).toHaveBeenCalledTimes(1);
    expect(fc.features).toHaveLength(1);
    expect(fc.features[0].properties.asr).toBe('fb');
    expect(fc.features[0].properties.owner).toBe('WEYERHAEUSER COMPANY');
  });

  it('present but malformed file → also falls back rather than showing no towers', async () => {
    stubFetch({ head: () => true, json: () => ({ unexpected: 'shape' }) });
    duckLoadTowerPoints.mockResolvedValue([] as TowerRow[]);

    const fc = await loadNationalTowers(['05']);
    expect(duckLoadTowerPoints).toHaveBeenCalledTimes(1);
    expect(fc).toEqual({ type: 'FeatureCollection', features: [] });
  });
});
