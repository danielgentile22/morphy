/**
 * Cosmetic display metadata for the controlled-vocab tags — colour tone, short
 * label, and a one-line meaning (lifted from PLAN.md §5) shown as a tooltip.
 *
 * The *value lists* that drive filters come from `index.json`'s `vocab` (so the
 * UI tracks the schema). This file only styles values it recognises; an
 * unrecognised value still renders as a neutral chip, so a new vocab entry is
 * never dropped — it just looks plain until styled here.
 */

import type { CardStatus } from './audit-data';

/** Maps to a CSS class `.chip--<tone>`; `cat` = neutral categorical. */
export type Tone = 'good' | 'ok' | 'warn' | 'bad' | 'muted' | 'cat';

export interface TagMeta {
  label: string;
  tone: Tone;
  title: string;
}

export const DIMENSION_LABELS: Record<string, string> = {
  confidence: 'Confidence',
  upstream_origin: 'Upstream origin',
  freshness_risk: 'Freshness risk',
  derivation_risk: 'Derivation risk',
  verifiability: 'Verifiability',
};

/** Per-dimension, per-value display metadata. `upstream_origin` is rendered as
 *  a neutral category (PLAN: origin "grants no trust by itself"), so no good/bad
 *  ramp — only confidence + the three risk/verifiability axes carry tone. */
const META: Record<string, Record<string, TagMeta>> = {
  confidence: {
    high: { label: 'high', tone: 'good', title: 'Act on a single instance directly.' },
    medium: { label: 'medium', tone: 'warn', title: 'Verify per-instance before betting money.' },
    low: { label: 'low', tone: 'bad', title: 'A heuristic guess — never bet money on it.' },
  },
  upstream_origin: {
    measured: { label: 'measured', tone: 'cat', title: 'The source surveyed/measured the value.' },
    official_filing: { label: 'official filing', tone: 'cat', title: 'A regulated filing of record.' },
    self_reported: { label: 'self-reported', tone: 'cat', title: 'Reported by the subject; unverified by the source.' },
    hand_keyed: { label: 'hand-keyed', tone: 'cat', title: 'Manually entered by a clerk/assessor.' },
    modeled: { label: 'modeled', tone: 'cat', title: 'Computed/estimated by the source.' },
    unknown: { label: 'unknown', tone: 'muted', title: 'Acquisition method not established.' },
  },
  freshness_risk: {
    low: { label: 'low', tone: 'good', title: 'Unlikely to be stale vs reality.' },
    medium: { label: 'medium', tone: 'warn', title: 'May lag reality; check recency.' },
    high: { label: 'high', tone: 'bad', title: 'Likely stale; staleness is material.' },
    unknown: { label: 'unknown', tone: 'muted', title: 'Staleness unmeasurable (no date at source).' },
  },
  derivation_risk: {
    none: { label: 'none', tone: 'good', title: 'Raw passthrough — we inject no error.' },
    low: { label: 'low', tone: 'ok', title: 'Minor transformation error injected by us.' },
    medium: { label: 'medium', tone: 'warn', title: 'Meaningful error injected by our derivation.' },
    high: { label: 'high', tone: 'bad', title: 'Our derivation injects substantial error.' },
  },
  verifiability: {
    per_instance_checkable: { label: 'per-instance', tone: 'good', title: 'You can confirm a single instance.' },
    sample_checkable: { label: 'sample', tone: 'warn', title: 'Checkable only in aggregate / by sample.' },
    uncheckable: { label: 'uncheckable', tone: 'bad', title: 'No way to confirm a single instance.' },
  },
};

export function tagMeta(dimension: string, value: string): TagMeta {
  return (
    META[dimension]?.[value] ?? {
      label: value.replace(/_/g, ' '),
      tone: 'cat',
      title: value,
    }
  );
}

const STATUS_META: Record<CardStatus, TagMeta> = {
  done: { label: 'done', tone: 'good', title: 'Audited; verdicts earned.' },
  in_progress: { label: 'in progress', tone: 'warn', title: 'Audit underway.' },
  todo: { label: 'todo', tone: 'muted', title: 'Not yet audited.' },
  stale: { label: 'stale', tone: 'warn', title: 'Code/data moved since the audit.' },
  needs_redo: { label: 'needs re-do', tone: 'bad', title: 'A flagged correction is pending.' },
};

export function statusMeta(status: CardStatus): TagMeta {
  return STATUS_META[status] ?? { label: status, tone: 'cat', title: status };
}
