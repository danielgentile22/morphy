/**
 * DuckDB-WASM tower-points loader.
 *
 * One module-level engine, instantiated lazily on first use (the ~6 MB
 * WASM is loaded async). `loadTowerPoints` reads each state's slim
 * `towers.parquet` over HTTP Range and unions them for the
 * structures-first map — the fallback when the precomputed
 * `composite/towers.json` is absent (PRD #163).
 *
 * The WASM + worker assets are bundled locally by Vite (the `?url`
 * imports) — no CDN fetch, consistent with the no-backend, PII-bearing,
 * local-only deployment.
 */

import * as duckdb from '@duckdb/duckdb-wasm';
import wasmEh from '@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url';
import wasmMvp from '@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url';
import workerEh from '@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url';
import workerMvp from '@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url';

/** The locally-bundled WASM/worker bundle spec — shared by the live engine's
 *  `doInit()` and the perf-probe's throwaway cold-init so both measure the
 *  same instantiation work. */
const DUCKDB_BUNDLES = {
  mvp: { mainModule: wasmMvp, mainWorker: workerMvp },
  eh: { mainModule: wasmEh, mainWorker: workerEh },
};

/** One slim tower row read off a state's `towers.parquet` for the
 *  structures-first map. `owner` is the landowner (`parcel_owner`);
 *  `tower_owner*` is the ASR registrant — the towerco/carrier lease
 *  counterparty — a different party entirely (audit M-b/M-c, #208). */
export interface TowerRow {
  asr: string;
  owner: string | null;
  height_m: number | null;
  state: string;
  active: boolean | null;
  lat: number;
  lon: number;
  /** Owner's Lead key (`display_cluster_id`), baked by the combined
   *  `towers.json` builder so the client need not re-hash 80k owner names
   *  on the tower load (#166). Absent on the per-state DuckDB path (and a
   *  stale file) — `rowsToFeatureCollection` then recomputes it. */
  cid?: string;
  /** Construction date — null when granted-but-not-built (~18% of ASR). */
  date_built?: string | null;
  tower_owner?: string | null;
  tower_owner_street?: string | null;
  tower_owner_city?: string | null;
  tower_owner_state?: string | null;
  tower_owner_zip?: string | null;
  tower_owner_phone?: string | null;
}

/** A source state's `towers.parquet` URL, keyed by FIPS for a stable
 *  DuckDB-registered filename. */
export interface TowerSource {
  fips: string;
  url: string;
}

/** Convert an Arrow query result into plain JS objects (BigInt → number). */
function toObjects<T>(table: { toArray(): unknown[] }): T[] {
  return table.toArray().map((row) => {
    const out: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(row as Record<string, unknown>)) {
      out[key] = typeof value === 'bigint' ? Number(value) : value;
    }
    return out as T;
  });
}

class DuckDbEngine {
  private db: duckdb.AsyncDuckDB | null = null;
  private initPromise: Promise<void> | null = null;

  /** Instantiate the WASM engine once (idempotent). */
  init(): Promise<void> {
    if (!this.initPromise) this.initPromise = this.doInit();
    return this.initPromise;
  }

  private async doInit(): Promise<void> {
    const bundle = await duckdb.selectBundle(DUCKDB_BUNDLES);
    const worker = new Worker(bundle.mainWorker!);
    const logger = new duckdb.ConsoleLogger(duckdb.LogLevel.ERROR);
    this.db = new duckdb.AsyncDuckDB(logger, worker);
    await this.db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  }

  /**
   * Slim tower points across the anchor states for the structures-first map.
   *
   * Reads only the columns the map needs from each state's `towers.parquet`
   * over HTTP Range (~6 MB total vs ~99 MB of raw towers GeoJSON), unioned
   * into one result. Runs on a dedicated connection so it can't collide with
   * the parcels filter pipeline on the shared one. The `sources` are assumed
   * to exist (the caller probes); a state whose query fails aborts the union,
   * so the caller filters to present files first.
   */
  async loadTowerPoints(sources: TowerSource[]): Promise<TowerRow[]> {
    if (sources.length === 0) return [];
    await this.init();
    const db = this.db!;
    const conn = await db.connect();
    try {
      const selects: string[] = [];
      for (const s of sources) {
        const file = `towers_${s.fips}.parquet`;
        const absolute = new URL(s.url, location.href).href;
        try {
          await db.dropFile(file);
        } catch {
          // not registered yet — fine
        }
        await db.registerFileURL(file, absolute, duckdb.DuckDBDataProtocol.HTTP, false);
        selects.push(
          // asr = the union-wide per-antenna key (_source_row_id): the FCC
          // registration number on FCC rows, the FAA obstacle number on FAA
          // rows — asr_number is FCC-only since the M-i split (#215).
          `SELECT CAST(_source_row_id AS VARCHAR) AS asr, ` +
            `CAST(parcel_owner AS VARCHAR) AS owner, ` +
            `CAST(height_m AS DOUBLE) AS height_m, ` +
            `CAST(state AS VARCHAR) AS state, ` +
            `CAST(is_active AS BOOLEAN) AS active, ` +
            `CAST(lat AS DOUBLE) AS lat, CAST(lon AS DOUBLE) AS lon, ` +
            `CAST(date_built AS VARCHAR) AS date_built, ` +
            `CAST(owner_name AS VARCHAR) AS tower_owner, ` +
            `CAST(owner_street AS VARCHAR) AS tower_owner_street, ` +
            `CAST(owner_city AS VARCHAR) AS tower_owner_city, ` +
            `CAST(owner_state AS VARCHAR) AS tower_owner_state, ` +
            `CAST(owner_zip AS VARCHAR) AS tower_owner_zip, ` +
            `CAST(owner_phone AS VARCHAR) AS tower_owner_phone ` +
            `FROM parquet_scan('${file}') WHERE lat IS NOT NULL AND lon IS NOT NULL`,
        );
      }
      const table = await conn.query(selects.join('\nUNION ALL\n'));
      return toObjects<TowerRow>(table);
    } finally {
      await conn.close();
    }
  }
}

export const duckDb = new DuckDbEngine();

/**
 * Perf-probe (PRD #163 / #164): time a DuckDB-WASM cold init in *isolation*.
 *
 * Spins up a brand-new, throwaway engine — independent of the shared singleton's
 * lifecycle — so the "DuckDB on the tower critical path" number is measured
 * clean even after the app has already inited DuckDB elsewhere. Mirrors
 * `doInit()` (selectBundle → Worker → instantiate → connect) and times the whole
 * sequence, then fully tears the throwaway engine down. Returns elapsed ms.
 *
 * For a truly *cold* number, run this on a fresh page load on a route that has
 * not yet touched DuckDB (e.g. the Dashboard) with the HTTP cache disabled —
 * see `scripts/perf/README.md`.
 */
export async function probeColdInit(): Promise<number> {
  const t0 = performance.now();
  const bundle = await duckdb.selectBundle(DUCKDB_BUNDLES);
  const worker = new Worker(bundle.mainWorker!);
  const db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(duckdb.LogLevel.ERROR), worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  const conn = await db.connect();
  const ms = performance.now() - t0;
  await conn.close();
  await db.terminate();
  worker.terminate();
  return ms;
}

// Dev-only perf-probe handle (PRD #164): exposes the isolated cold-init so the
// browser probe in `scripts/perf/` can time it via the bundled WASM assets.
// Gated to dev so it never ships in the production bundle (the probe is
// local-stack only).
if (typeof window !== 'undefined' && import.meta.env.DEV) {
  (window as unknown as { __probeColdInit?: typeof probeColdInit }).__probeColdInit = probeColdInit;
}
