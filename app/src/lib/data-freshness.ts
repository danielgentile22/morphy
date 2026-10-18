/**
 * Data-freshness read-out (#235) — user-visible projection of the
 * deploy-time `freshness.json` snapshot (scripts/export_freshness.py),
 * written into the served composite and fetched behind the same session
 * gate as every other `/data/processed/*` file. Read-only: the app only
 * renders what the last deploy exported — no puller state, no backend tables.
 *
 * Pure + `now`-injected (repo convention) so rows unit-test without a
 * network or a clock.
 */

import { freshnessUrl } from './data';

/** Subset of the freshness.json contract this read-out needs. */
export interface FreshnessSource {
  title: string;
  kind: 'fetched' | 'derived';
  last_pulled: string | null;
}

export interface FreshnessDoc {
  generated_at: string;
  sources: FreshnessSource[];
}

// Human-friendly names, in display order. Keys are the exporter's
// stable dossier titles (scripts/export_freshness.py AUDIT_SOURCE_MAP).
const LABELS: Record<string, string> = {
  'fcc-asr': 'Cell towers (FCC ASR)',
  'faa-dof': 'FAA obstacles (DOF)',
  'carrier-identification': 'Carrier identification (FCC ULS)',
  'parcels-AR': 'Arkansas parcels',
  'parcels-FL': 'Florida parcels',
  'parcels-MT': 'Montana parcels',
  'parcels-WV': 'West Virginia parcels',
  'distress-overlays': 'Distress overlays (HUD / ARC / USDA)',
  'billboards-FL': 'Florida billboards',
  'solar-feeds': 'Solar feeds (USPVDB / EIA)',
};

export interface FreshnessRow {
  label: string;
  /** "Jun 12, 2026", or null when never pulled — render as an em dash. */
  refreshed: string | null;
  /** "today" / "yesterday" / "N days ago" / "never pulled". */
  ago: string;
}

const DAY_MS = 86_400_000;

/** ISO timestamp → "Jun 12, 2026" (UTC, so tests and prod agree), else null. */
export function fmtDate(iso: string | null): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

function relative(iso: string | null, now: Date): string {
  if (!iso) return 'never pulled';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 'never pulled';
  // Clock skew that puts the pull in the future reads as 0, never negative.
  const days = Math.max(0, Math.floor((now.getTime() - t) / DAY_MS));
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  return `${days} days ago`;
}

/** Fetched sources only, in LABELS order. Unmapped titles trail name-sorted
 *  with a de-slugged label, so a new exporter entry shows up rather than
 *  silently dropping. Derived layers are excluded — they rebuild with every
 *  deploy and have no pull date to show. */
export function freshnessRows(doc: FreshnessDoc, now: Date): FreshnessRow[] {
  const order = Object.keys(LABELS);
  const rank = (t: string): number => {
    const i = order.indexOf(t);
    return i === -1 ? order.length : i;
  };
  return doc.sources
    .filter((s) => s.kind === 'fetched')
    .sort((a, b) => rank(a.title) - rank(b.title) || a.title.localeCompare(b.title))
    .map((s) => ({
      label: LABELS[s.title] ?? s.title.replace(/-/g, ' '),
      refreshed: fmtDate(s.last_pulled),
      ago: relative(s.last_pulled, now),
    }));
}

/** Load the deploy-baked snapshot; null when absent / unauthorized / invalid —
 *  callers render a quiet placeholder, never an error (the snapshot is a
 *  deploy artifact and legitimately missing in dev). */
export async function loadFreshness(): Promise<FreshnessDoc | null> {
  try {
    const res = await fetch(freshnessUrl(), { cache: 'no-store' });
    if (!res.ok) return null;
    const doc = (await res.json()) as FreshnessDoc;
    return Array.isArray(doc?.sources) ? doc : null;
  } catch {
    return null;
  }
}
