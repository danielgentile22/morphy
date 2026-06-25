/**
 * Types + loader for the audit artifacts. `index.json` is the single source of
 * truth (PLAN §1); these interfaces mirror it but stay tolerant (the loader
 * never transforms values — the UI reads them verbatim). Markdown dossiers are
 * fetched on demand. Everything is fetched at runtime from `<base>data/*` so a
 * re-run that rewrites the files shows up on a refresh — see serve-audit-data.ts
 * (dev/preview) and the deployed Caddy `/audit/data/*` route (prod).
 */

import type { FreshnessDoc } from './freshness';
import type { FixesDoc } from './fixes';

export type Confidence = 'high' | 'medium' | 'low';
export type CardStatus = 'todo' | 'in_progress' | 'done' | 'stale' | 'needs_redo';

/** The controlled vocabularies (PLAN §5). Drives every filter + legend so the
 *  UI stays correct as the schema evolves — never hardcode the value lists. */
export interface Vocab {
  status: string[];
  upstream_origin: string[];
  freshness_risk: string[];
  derivation_risk: string[];
  verifiability: string[];
  confidence: string[];
}

/** The five controlled-vocab tags every signal carries. */
export interface SignalTags {
  upstream_origin: string;
  freshness_risk: string;
  derivation_risk: string;
  verifiability: string;
  confidence: Confidence;
}

/** The keys of SignalTags, in scan-first display order (confidence leads). */
export const TAG_DIMENSIONS = [
  'confidence',
  'upstream_origin',
  'freshness_risk',
  'derivation_risk',
  'verifiability',
] as const;
export type TagDimension = (typeof TAG_DIMENSIONS)[number];

export interface Signal {
  id: string;
  card: string;
  surface: string;
  priority: string | null;
  tags: SignalTags;
  verdict: string;
  /** `file.md#anchor`; the anchor is the signal id in the dossier heading. */
  dossier: string;
}

export interface AuditBasis {
  commit: string | null;
  data_snapshot: string | null;
  source_docs: string[];
}

export interface Card {
  id: string;
  title: string;
  priority: string | null;
  status: CardStatus;
  methods_done: { A: boolean; B: boolean; C: boolean };
  output_file: string;
  last_audited: string | null;
  audit_basis: AuditBasis;
  /** Free-text notes are open-ended (`t00_note`/`t90_note`/`redo_note`/…); read
   *  them via {@link cardNotes} rather than naming each key here. */
  [key: `${string}_note`]: string | undefined;
}

export interface AuditIndex {
  schema_version: number;
  generated: string;
  audit_basis: AuditBasis;
  note: string;
  vocab: Vocab;
  cards: Card[];
  signals: Signal[];
}

/** A card's free-text notes, in file order, with a human label per key. */
export interface CardNote {
  key: string;
  label: string;
  text: string;
}

const NOTE_LABELS: Record<string, string> = {
  t00_note: 'T-00 enumeration note',
  t90_note: 'T-90 reconciliation note',
  t91_note: 'T-91 verification note',
  t21_note: 'T-21 completion note',
  t30_note: 'T-30 completion note',
  redo_note: 'Re-do note',
};

export function cardNotes(card: Card): CardNote[] {
  const out: CardNote[] = [];
  for (const [key, value] of Object.entries(card)) {
    if (key.endsWith('_note') && typeof value === 'string') {
      out.push({ key, label: NOTE_LABELS[key] ?? key, text: value });
    }
  }
  return out;
}

// `<base>data/` — `/audit/data/` in the deployed build, served by Caddy (prod)
// or the serve-audit-data plugin (dev/preview). One path, every environment.
const DATA_BASE = `${import.meta.env.BASE_URL}data/`;

export async function fetchIndex(): Promise<AuditIndex> {
  const res = await fetch(`${DATA_BASE}index.json`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to load index.json (HTTP ${res.status})`);
  return res.json() as Promise<AuditIndex>;
}

// `freshness.json` is a deploy-time snapshot (M8 exporter) and may be absent —
// it's git-ignored and only baked in at deploy. Any failure (404 before it's
// generated, or a parse error) degrades to `null` rather than throwing, so the
// "What needs updating" tab shows its "not yet generated" state and the rest of
// the app is unaffected. See lib/freshness.ts for the doc shape.
export async function fetchFreshness(): Promise<FreshnessDoc | null> {
  try {
    const res = await fetch(`${DATA_BASE}freshness.json`, { cache: 'no-store' });
    if (!res.ok) return null;
    return (await res.json()) as FreshnessDoc;
  } catch {
    return null;
  }
}

// `fixes.json` is the hand-authored fix-status board (companion to
// fix-ledger.md). Like freshness.json it's an optional sibling artifact —
// degrade to `null` on any failure so the Fixes tab shows its "not yet
// generated" state and the rest of the app is unaffected. See lib/fixes.ts.
export async function fetchFixes(): Promise<FixesDoc | null> {
  try {
    const res = await fetch(`${DATA_BASE}fixes.json`, { cache: 'no-store' });
    if (!res.ok) return null;
    return (await res.json()) as FixesDoc;
  } catch {
    return null;
  }
}

// In-session cache: a dossier is immutable within a page load. A re-run +
// refresh reboots the app and re-fetches everything, so this never serves stale
// data across the "auto-populate on rerun" boundary.
const docCache = new Map<string, Promise<string>>();

export function fetchDoc(file: string): Promise<string> {
  let pending = docCache.get(file);
  if (!pending) {
    pending = fetch(`${DATA_BASE}${file}`, { cache: 'no-store' })
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load ${file} (HTTP ${res.status})`);
        return res.text();
      })
      .catch((err: unknown) => {
        docCache.delete(file); // let a later view retry
        throw err;
      });
    docCache.set(file, pending);
  }
  return pending;
}
