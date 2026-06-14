// Map-app perf-probe — isolated DuckDB-WASM cold-init pass (PRD #163 / #164,
// category B).
//
// Measures the ~6 MB DuckDB-WASM engine's cold init in ISOLATION — a brand-new
// throwaway instance, independent of the app's shared singleton — so the
// "DuckDB on the tower critical path" number is clean.
//
// Run this on a FRESH page load on the **Dashboard** (route `#/` — NOT
// `#/explore`), with the HTTP cache disabled (reload with ignoreCache). On the
// Dashboard the app has not yet touched DuckDB, so this throwaway init is the
// first WASM instantiate on the page = genuinely cold. (Run on `#/explore` and
// the number is warm — the tower path already inited DuckDB today.)
//
// Pass the whole file as the `function` argument to chrome-devtools
// `evaluate_script`, or paste into the DevTools console prefixed with `await`.
// Returns the cold-init milliseconds (or an error object). No PII.

async () => {
  // On the Dashboard the duckdb module isn't imported yet, so the dev-only
  // window.__probeColdInit handle isn't attached. Force-load the source module
  // (Vite dev serves it at this stable path) to attach it, then time a fresh
  // throwaway init. The import itself only evaluates the module — it does NOT
  // init the engine — so the timed instantiate stays cold.
  if (typeof window.__probeColdInit !== 'function') {
    try {
      await import('/src/lib/duckdb.ts');
    } catch (e) {
      return { error: `could not import /src/lib/duckdb.ts — is this the dev stack? ${String(e)}` };
    }
  }
  if (typeof window.__probeColdInit !== 'function') {
    return { error: 'window.__probeColdInit still missing after import — DEV build only.' };
  }
  const ms = await window.__probeColdInit();
  return {
    capturedAt: new Date().toISOString(),
    href: location.href,
    duckdbColdInitMs: Math.round(ms * 10) / 10,
    note: 'Isolated throwaway instance. Cold only on a fresh non-Explore load with cache disabled.',
  };
}
