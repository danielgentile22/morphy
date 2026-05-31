// Vitest global setup.
//
// We resolve Svelte's *browser* entry under Vitest (see vite.config.ts) so
// component tests can `mount()` in jsdom. That same browser condition makes
// `@duckdb/duckdb-wasm` resolve its browser build, which references `Worker`
// at import time — absent in jsdom. The duckdb-touching unit tests are all
// pure-function tests (query building, row→GeoJSON) that never start a real
// DuckDB, so a no-op `Worker` stub is enough to let the module import.
class WorkerStub {
  onmessage: ((e: unknown) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  postMessage(): void {}
  terminate(): void {}
  addEventListener(): void {}
  removeEventListener(): void {}
  dispatchEvent(): boolean {
    return false;
  }
}

if (typeof (globalThis as { Worker?: unknown }).Worker === 'undefined') {
  (globalThis as { Worker?: unknown }).Worker = WorkerStub;
}
