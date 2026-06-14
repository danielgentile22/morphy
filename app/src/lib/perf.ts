// Passive perf instrumentation for the committed map-app perf-probe
// (PRD #163 / #164). These are User-Timing marks/measures ONLY — zero
// behavioural effect on the app. The probe (`scripts/perf/`) reads them back
// off `performance` on a cold Explore reload, so "time-to-first-tower" is a
// real measured number captured identically on every run rather than eyeballed.
//
// Keep the `perf:towers` measure bracketing whatever the tower-load seam
// becomes (today DuckDB-WASM union; after PRD #163 PR3 a `towers.json` fetch),
// so the post-PRD re-measure (#169) compares the same span as the baseline.

/** Mark names — stable identifiers the probe queries by. */
export const TOWERS_START_MARK = 'perf:towers:start';
export const TOWERS_DONE_MARK = 'perf:towers:done';
/** The single measure spanning the tower critical path; carries the feature
 *  count in `.detail.features`. The probe reads `.duration` + `.detail`. */
export const TOWERS_MEASURE = 'perf:towers';

/** Best-effort: the User Timing API is unavailable / partial in some test
 *  envs (happy-dom), and instrumentation must never throw into the app path. */
function safe(fn: () => void): void {
  try {
    fn();
  } catch {
    /* User Timing unsupported here — instrumentation is best-effort only. */
  }
}

/** Stamp the start of the tower critical path. Clears a prior start so a
 *  re-load (e.g. retry after error) measures the latest attempt, not the first. */
export function markTowersStart(): void {
  safe(() => performance.clearMarks(TOWERS_START_MARK));
  safe(() => performance.mark(TOWERS_START_MARK));
}

/** Stamp tower-data-ready (the FeatureCollection is built — first dots are
 *  about to render) and emit the `perf:towers` measure carrying the feature
 *  count. No-ops cleanly if the start mark never ran. */
export function markTowersDone(featureCount: number): void {
  safe(() => performance.mark(TOWERS_DONE_MARK));
  safe(() => performance.clearMeasures(TOWERS_MEASURE));
  safe(() =>
    performance.measure(TOWERS_MEASURE, {
      start: TOWERS_START_MARK,
      end: TOWERS_DONE_MARK,
      detail: { features: featureCount },
    }),
  );
}
