/**
 * Types + pure helpers for the Fixes tab. `fixes.json` is a hand-authored
 * companion to the audit (prose in fix-ledger.md) — the live status board for
 * the data-audit fixes. An agent marks a fix done by flipping its `status` to
 * `"done"` in the file; a redeploy rebakes it and this tab updates (same
 * "auto-populate on rerun" contract as the rest of the site). Loaded
 * degrade-to-null like freshness.json, so its absence never blocks the app.
 *
 * Only EASY/MEDIUM fixes carry a status (they're units of work). MACRO/INHERENT
 * are display-only — the design reworks you hunt for and the un-fixable source
 * caveats — so they have no `status`/`ripple`.
 */

export type FixBucket = 'easy' | 'medium' | 'macro' | 'inherent';
export type FixStatus = 'todo' | 'done';

export interface Fix {
  id: string;
  bucket: FixBucket;
  title: string;
  signal: string;
  card: string;
  /** EASY/MEDIUM/MACRO carry a `problem`; INHERENT folds its caveat into `action`. */
  problem?: string;
  /** The fix (easy), the call-to-make (medium), the rework (macro), or the caveat (inherent). */
  action: string;
  /** What the edit touches beyond its own file. EASY/MEDIUM only. */
  ripple?: string;
  /** `file.md#anchor` into the audit dossiers. */
  dossier: string;
  /** Present + meaningful only for checkable buckets (EASY/MEDIUM). */
  status?: FixStatus;
}

export interface FixesDoc {
  schema_version: number;
  generated: string;
  basis: string;
  note: string;
  buckets: Record<FixBucket, string>;
  fixes: Fix[];
}

/** Display order: actionable first, then the things you only review. */
export const BUCKET_ORDER: FixBucket[] = ['easy', 'medium', 'macro', 'inherent'];

export const BUCKET_LABEL: Record<FixBucket, string> = {
  easy: 'Easy',
  medium: 'Medium',
  macro: 'Macro',
  inherent: 'Inherent',
};

/** Buckets whose fixes are tickable units of work (carry a status). */
const CHECKABLE = new Set<FixBucket>(['easy', 'medium']);

export function isCheckable(bucket: FixBucket): boolean {
  return CHECKABLE.has(bucket);
}

export interface FixGroup {
  bucket: FixBucket;
  label: string;
  meaning: string;
  checkable: boolean;
  fixes: Fix[];
  done: number;
  total: number;
}

/** Group fixes by bucket in display order, with per-bucket done/total (0 total
 *  for the non-checkable buckets). Empty buckets are dropped. */
export function groupFixes(doc: FixesDoc): FixGroup[] {
  const groups: FixGroup[] = [];
  for (const bucket of BUCKET_ORDER) {
    const fixes = doc.fixes.filter((f) => f.bucket === bucket);
    if (fixes.length === 0) continue;
    const checkable = isCheckable(bucket);
    groups.push({
      bucket,
      label: BUCKET_LABEL[bucket],
      meaning: doc.buckets[bucket] ?? '',
      checkable,
      fixes,
      done: checkable ? fixes.filter((f) => f.status === 'done').length : 0,
      total: checkable ? fixes.length : 0,
    });
  }
  return groups;
}

/** Overall done/total across the checkable buckets only — drives the header
 *  progress read ("7 of 27 fixes done"). */
export function overallProgress(doc: FixesDoc): { done: number; total: number } {
  let done = 0;
  let total = 0;
  for (const f of doc.fixes) {
    if (!isCheckable(f.bucket)) continue;
    total += 1;
    if (f.status === 'done') done += 1;
  }
  return { done, total };
}
