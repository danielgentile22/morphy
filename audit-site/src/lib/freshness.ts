/**
 * M9 · Client freshness model (deep module). Pure projection of the baked
 * `freshness.json` snapshot against *today*, mirroring the puller manifest's
 * `SourceEntry.freshness()` (scripts/fetch/manifest.py) so the due/overdue
 * countdown advances day-by-day from the last deploy with no redeploy.
 *
 * The snapshot bakes a `status` at export time; we deliberately *recompute* it
 * here from `last_pulled` / `cadence_days` / `next_check` vs `now`, using the
 * same 50 %-of-cadence due-soon threshold — so the two never drift but the page
 * stays live between deploys. Derived ("rebuilt, not fetched") sources keep
 * their `rebuilt` status verbatim: there's no pull date to age.
 *
 * Everything here is pure and `now`-injected, so the thresholds unit-test
 * against the same fixtures as the Python exporter (tests/test_export_freshness).
 */

/** The freshness vocab — fetched sources cycle fresh→due_soon→stale; a source
 *  with no cadence/pull is `unknown`; derived data is `rebuilt`. Mirrors
 *  `fetch.manifest.FRESHNESS_*` + the exporter's `STATUS_REBUILT`. */
export type FreshnessStatus = 'fresh' | 'due_soon' | 'stale' | 'unknown' | 'rebuilt';

/** One audit source's pull state — the `freshness.json` `sources[]` entry. The
 *  baked `status` is what the exporter computed at deploy time; the live model
 *  recomputes it, so treat it as a fallback hint, not the source of truth. */
export interface FreshnessSource {
  id: string;
  title: string;
  kind: 'fetched' | 'derived';
  manifest_source_ids: string[];
  last_pulled: string | null;
  cadence_days: number | null;
  next_check: string | null;
  status: FreshnessStatus;
  rebuilt_not_fetched: boolean;
}

/** The whole `freshness.json` document (see scripts/export_freshness.py). */
export interface FreshnessDoc {
  schema_version: number;
  generated_at: string;
  manifest: { present: boolean; last_full_check: string | null };
  note: string;
  sources: FreshnessSource[];
}

// Mirrors `fetch.manifest.DUE_SOON_FRACTION` — past this fraction of one cadence
// window (i.e. half-way to the next check) a source reads "due soon". Keep in
// lockstep with the puller; the exporter test pins the same boundary.
export const DUE_SOON_FRACTION = 0.5;
const DAY_MS = 86_400_000;

function parseIso(iso: string | null): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

/** Whole days between `last_pulled` and `now` (floored, never negative — a clock
 *  skew that puts the pull in the future reads as 0), or `null` if never pulled.
 *  Mirrors `SourceEntry.days_since_fetch`. */
export function daysSince(iso: string | null, now: Date): number | null {
  const t = parseIso(iso);
  if (t === null) return null;
  return Math.max(0, Math.floor((now.getTime() - t) / DAY_MS));
}

/** The live status of a fetched source vs `now`, recomputed from its baked
 *  cadence + next-check. Mirrors `SourceEntry.freshness()` exactly: no cadence
 *  or no next-check ⇒ `unknown` (no fabricated due-date); past next-check ⇒
 *  `stale`; past 50 % of the window ⇒ `due_soon`; else `fresh`. */
function liveStatus(src: FreshnessSource, now: Date): FreshnessStatus {
  if (src.cadence_days === null) return 'unknown';
  const nra = parseIso(src.next_check);
  if (nra === null) return 'unknown';
  const t = now.getTime();
  if (t >= nra) return 'stale';
  const dueSoonAt = nra - src.cadence_days * DUE_SOON_FRACTION * DAY_MS;
  if (t >= dueSoonAt) return 'due_soon';
  return 'fresh';
}

export interface FreshnessVerdict {
  /** Recomputed-against-`now` status — what the UI shows (not the baked value). */
  status: FreshnessStatus;
  /** Whole days since the last pull, or `null` for never-pulled / derived. */
  daysAgo: number | null;
}

/** The verdict for one source against `now`. Derived data ("rebuilt, not
 *  fetched") short-circuits to `rebuilt` with no pull age. Pure. */
export function computeFreshness(src: FreshnessSource, now: Date): FreshnessVerdict {
  if (src.rebuilt_not_fetched || src.kind === 'derived') {
    return { status: 'rebuilt', daysAgo: null };
  }
  return { status: liveStatus(src, now), daysAgo: daysSince(src.last_pulled, now) };
}

/** A source paired with its live verdict — the shared shape the page table and
 *  the Overview callout both render. */
export interface FreshnessRow {
  source: FreshnessSource;
  verdict: FreshnessVerdict;
}

/** How "needy" each status is — drives worst-first ordering + the callout tone.
 *  Overdue leads; rebuilt (nothing to do) trails. */
const SEVERITY: Record<FreshnessStatus, number> = {
  stale: 4,
  due_soon: 3,
  fresh: 2,
  unknown: 1,
  rebuilt: 0,
};

/** Every source projected to a live verdict, most-needy-first (then id-stable).
 *  Pure; `now` injected so a re-render against a later day reorders without a
 *  redeploy. */
export function freshnessRows(doc: FreshnessDoc, now: Date): FreshnessRow[] {
  return doc.sources
    .map((source) => ({ source, verdict: computeFreshness(source, now) }))
    .sort(
      (a, b) =>
        SEVERITY[b.verdict.status] - SEVERITY[a.verdict.status] ||
        a.source.id.localeCompare(b.source.id),
    );
}

export interface FreshnessSummary {
  /** Live status → count, across every source. */
  counts: Record<FreshnessStatus, number>;
  /** Overdue sources, worst-first — the headline "needs refreshing" list. */
  stale: FreshnessRow[];
  /** Sources due soon — the softer bucket. */
  dueSoon: FreshnessRow[];
}

/** Roll the rows up for the Overview callout: per-status counts + the overdue /
 *  due-soon buckets. Pure. */
export function freshnessSummary(rows: FreshnessRow[]): FreshnessSummary {
  const counts: Record<FreshnessStatus, number> = {
    fresh: 0,
    due_soon: 0,
    stale: 0,
    unknown: 0,
    rebuilt: 0,
  };
  for (const r of rows) counts[r.verdict.status]++;
  return {
    counts,
    stale: rows.filter((r) => r.verdict.status === 'stale'),
    dueSoon: rows.filter((r) => r.verdict.status === 'due_soon'),
  };
}

// ── presentation helpers (pure, so labels stay testable + consistent) ─────────

/** Status → plain-language badge (reuses the audit chip tone palette). Overdue
 *  reads as the alarm; rebuilt/unknown sit muted (no action implied). */
export function statusBadge(status: FreshnessStatus): { label: string; tone: 'good' | 'warn' | 'bad' | 'muted' } {
  switch (status) {
    case 'fresh':
      return { label: 'Fresh', tone: 'good' };
    case 'due_soon':
      return { label: 'Due soon', tone: 'warn' };
    case 'stale':
      return { label: 'Overdue', tone: 'bad' };
    case 'rebuilt':
      return { label: 'Rebuilt', tone: 'muted' };
    default:
      return { label: 'No schedule', tone: 'muted' };
  }
}

/** Status → one-line meaning for the table / tooltips. */
export function statusBlurb(status: FreshnessStatus): string {
  switch (status) {
    case 'fresh':
      return 'Pulled recently — well within its refresh window.';
    case 'due_soon':
      return 'Past halfway to its next recommended check — refresh soon.';
    case 'stale':
      return 'Past its next recommended check — refresh now.';
    case 'rebuilt':
      return 'Rebuilt by the pipeline, not pulled — no fetch date to age.';
    default:
      return 'No refresh cadence at the source — staleness can’t be judged.';
  }
}

/** `cadence_days → friendly cadence`. Common windows get a word; everything else
 *  falls back to "every N days". `null` (derived / no cadence) → an em dash. */
export function cadenceLabel(days: number | null): string {
  if (days === null) return '—';
  const named: Record<number, string> = {
    1: 'Daily',
    7: 'Weekly',
    14: 'Every 2 weeks',
    30: 'Monthly',
    31: 'Monthly',
    90: 'Quarterly',
    180: 'Twice a year',
    365: 'Yearly',
  };
  return named[days] ?? `Every ${days} days`;
}

/** `daysAgo → "today" / "yesterday" / "N days ago"`. `null` → "never pulled". */
export function relativeDays(daysAgo: number | null): string {
  if (daysAgo === null) return 'never pulled';
  if (daysAgo === 0) return 'today';
  if (daysAgo === 1) return 'yesterday';
  return `${daysAgo} days ago`;
}
