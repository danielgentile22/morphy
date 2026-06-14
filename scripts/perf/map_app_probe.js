// Map-app perf-probe — Explore pass (PRD #163 / #164).
//
// Captures the in-page metrics that define the perf acceptance bar on an
// authenticated **Explore cold reload** of the LOCAL dev stack. Pass the whole
// file as the `function` argument to the chrome-devtools MCP `evaluate_script`
// tool (it is a single async arrow function), or paste it into the DevTools
// console prefixed with `await`. Returns a plain JSON object — no PII, only
// sizes / timings / counts.
//
// Run AFTER the Explore cold reload has settled (tower dots visible). The
// isolated DuckDB cold-init is a SEPARATE pass — see duckdb_cold_init.js — so
// it is measured on a fresh instance, uncontaminated by the app's own init.
//
// See scripts/perf/README.md for the full run sequence and what each number
// means / where it comes from.
//
//   Metrics emitted here:
//     - timeToFirstTowerMs   (the `perf:towers` User-Timing measure)
//     - towerFeatureCount    (from the measure's detail)
//     - ownersFilter         (transfer bytes + parse ms + owner count)
//     - towerPathRequests     (resource-timing view — main-thread only; see note)
//     - parcelTileRequests    (resource-timing view of parcels.pmtiles range GETs)
//
//   Metrics that come from elsewhere (documented in README):
//     - isolated DuckDB cold-init ms                       -> duckdb_cold_init.js
//     - tower-path request count incl. DuckDB worker GETs  -> Network panel
//     - per-state parcels.pmtiles on-disk sizes            -> pmtiles_sizes.py

async () => {
  const round = (n) => (Number.isFinite(n) ? Math.round(n * 10) / 10 : null);
  const OWNERS_FILTER_URL = '/data/processed/composite/owners_filter.json';

  // ── Time-to-first-tower + feature count (User-Timing measure the app emits) ──
  const towerMeasure = performance.getEntriesByName('perf:towers', 'measure').slice(-1)[0];
  const timeToFirstTowerMs = towerMeasure ? round(towerMeasure.duration) : null;
  const towerFeatureCount =
    (towerMeasure && towerMeasure.detail && towerMeasure.detail.features) ?? null;

  // ── owners_filter.json: transfer size + parse time + owner count ─────────────
  const ofEntry = performance
    .getEntriesByType('resource')
    .filter((e) => e.name.includes('owners_filter.json'))
    .slice(-1)[0];
  // Re-fetch the text so JSON.parse is timed in isolation (CPU-bound; transfer
  // is reported separately from the original cold load's resource entry).
  const ofText = await (await fetch(OWNERS_FILTER_URL)).text();
  const parseT0 = performance.now();
  const ofJson = JSON.parse(ofText);
  const ownersFilterParseMs = round(performance.now() - parseT0);
  const ownersFilter = {
    transferBytes: ofEntry ? ofEntry.transferSize : null,
    encodedBodyBytes: ofEntry ? ofEntry.encodedBodySize : null,
    transferMB: ofEntry ? round(ofEntry.transferSize / 1048576) : null,
    transferMs: ofEntry ? round(ofEntry.duration) : null,
    // transferSize is 0 when served from the memory/disk cache — a cold reload
    // (cache disabled) is required for a real transfer number; flagged here.
    fromCache: ofEntry ? ofEntry.transferSize === 0 : null,
    parseMs: ownersFilterParseMs,
    ownerCount: Array.isArray(ofJson.owners) ? ofJson.owners.length : null,
    textBytes: ofText.length,
  };

  // ── Request-count views from main-thread Resource Timing ─────────────────────
  // NOTE: DuckDB-WASM issues its parquet range GETs from its Web Worker, which
  // does NOT appear in this main-thread timeline. Use the chrome-devtools
  // Network panel (list_network_requests, filter "towers.parquet") for the
  // authoritative tower-path count. The number here is the main-thread slice
  // (the HEAD presence-probes + any main-thread GETs) — reported for context.
  const resources = performance.getEntriesByType('resource');
  const towerPathEntries = resources.filter((e) => e.name.includes('towers.parquet'));
  const parcelTileEntries = resources.filter((e) => e.name.includes('parcels.pmtiles'));

  return {
    capturedAt: new Date().toISOString(),
    href: location.href,
    metrics: {
      timeToFirstTowerMs,
      towerFeatureCount,
      ownersFilter,
      towerPathRequestsMainThread: towerPathEntries.length,
      parcelTileRequestsMainThread: parcelTileEntries.length,
    },
    notes: [
      'timeToFirstTowerMs is the perf:towers measure = probe + DuckDB init + union + marshal (data-ready, pre-paint).',
      'isolated DuckDB cold-init is a separate pass (duckdb_cold_init.js); breakdown = timeToFirstTowerMs - coldInitMs.',
      'tower-path + parcel-tile request COUNTS for the baseline come from the Network panel, not these main-thread numbers.',
      'parcels.pmtiles on-disk sizes come from scripts/perf/pmtiles_sizes.py.',
    ],
  };
}
