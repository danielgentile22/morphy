// Lead status state machine (ADR-061 / CONTEXT.md).
//
// Single status per Lead. The ladder branches after Contacted:
//
//   New ──▶ Researching ──▶ Contacted ──┬──▶ Interested ──▶ In Business
//                                       └──▶ Uninterested   (reopenable)
//
// Default = New. `in_business` (won) is the one true terminal — reachable
// only via `interested`, no way out. `uninterested` (lost/parked) is the
// closed-but-reopenable bucket: it can move back to ANY status so a
// mis-classified lead is never stranded. Re-saving the same status is
// allowed (saving a note without advancing).
//
// This MUST stay in lockstep with backend/app/lead_status.py — both encode
// the same ladder; the backend re-validates every write server-side.

export const STATUSES = [
  'new',
  'researching',
  'contacted',
  'interested',
  'in_business',
  'uninterested',
] as const;

export type LeadStatus = (typeof STATUSES)[number];

export const INITIAL_STATUS: LeadStatus = 'new';

export const STATUS_LABELS: Record<LeadStatus, string> = {
  new: 'New',
  researching: 'Researching',
  contacted: 'Contacted',
  interested: 'Interested',
  in_business: 'In Business',
  uninterested: 'Uninterested',
};

// Halo chip tone per status, for non-kanban surfaces (the Leads list, etc).
// Decorative only — the text label always rides along, so this stays
// colorblind-safe (meaning never on hue alone). `interested` uses the default
// primary chip (empty tone). The kanban (MyLeads) keeps its own --s-* lanes +
// glyph cue and does NOT use this.
export const STATUS_TONE: Record<
  LeadStatus,
  '' | 'neutral' | 'info' | 'warning' | 'success' | 'danger'
> = {
  new: 'neutral',
  researching: 'warning',
  contacted: 'info',
  interested: '',
  in_business: 'success',
  uninterested: 'danger',
};

// Closed/end-of-pipeline lanes — used for the kanban's "closed" visual
// treatment, NOT for transition-locking. `uninterested` shows as closed but
// is reopenable (see ALLOWED_TRANSITIONS); only `in_business` is truly locked.
export const TERMINAL_STATUSES: ReadonlySet<LeadStatus> = new Set([
  'in_business',
  'uninterested',
]);

// The My-Leads kanban lanes (Slice 5 / #51): every status *except* New, in
// ladder order. New owners live in Candidates, not the worklist;
// `uninterested` is rendered as a closed lane (still draggable back out).
export const KANBAN_LANES: readonly LeadStatus[] = STATUSES.filter((s) => s !== INITIAL_STATUS);

// Allowed *forward* transitions (identity handled separately). `uninterested`
// is the exception: a lost/parked lead can be reopened to ANY status, so a
// mis-click or change of heart is never a dead end. `in_business` stays a
// true terminal (won — no outgoing moves).
const ALLOWED_TRANSITIONS: Record<LeadStatus, readonly LeadStatus[]> = {
  new: ['researching'],
  researching: ['contacted', 'uninterested'],
  contacted: ['interested', 'uninterested'],
  interested: ['in_business', 'uninterested'],
  in_business: [],
  uninterested: ['new', 'researching', 'contacted', 'interested', 'in_business'],
};

export function isValidStatus(status: string): status is LeadStatus {
  return (STATUSES as readonly string[]).includes(status);
}

/** True if `from → to` is legal. Same-status (idempotent save) is legal. */
export function canTransition(from: string, to: string): boolean {
  if (!isValidStatus(from) || !isValidStatus(to)) return false;
  if (from === to) return true;
  return ALLOWED_TRANSITIONS[from].includes(to);
}
