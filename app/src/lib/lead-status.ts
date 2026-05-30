// Lead status state machine (ADR-061 / CONTEXT.md).
//
// Single status per Lead. The ladder branches after Contacted:
//
//   New ──▶ Researching ──▶ Contacted ──┬──▶ Interested ──▶ In Business
//                                       └──▶ Uninterested   (terminal)
//
// Default = New. `in_business` (won) and `uninterested` (lost) are
// terminal; `in_business` is reachable only via `interested`. Re-saving
// the same status is allowed (saving a note without advancing).
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

export const TERMINAL_STATUSES: ReadonlySet<LeadStatus> = new Set([
  'in_business',
  'uninterested',
]);

// The My-Leads kanban lanes (Slice 5 / #51): every status *except* New, in
// ladder order. New owners live in Candidates, not the worklist;
// `uninterested` is rendered as a closed/terminal lane.
export const KANBAN_LANES: readonly LeadStatus[] = STATUSES.filter((s) => s !== INITIAL_STATUS);

// Allowed *forward* transitions (identity handled separately).
const ALLOWED_TRANSITIONS: Record<LeadStatus, readonly LeadStatus[]> = {
  new: ['researching'],
  researching: ['contacted', 'uninterested'],
  contacted: ['interested', 'uninterested'],
  interested: ['in_business', 'uninterested'],
  in_business: [],
  uninterested: [],
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

/** Statuses selectable from `from` (itself + legal next), in ladder order. */
export function nextStatuses(from: string): LeadStatus[] {
  if (!isValidStatus(from)) return [];
  const allowed = new Set<LeadStatus>([from, ...ALLOWED_TRANSITIONS[from]]);
  return STATUSES.filter((s) => allowed.has(s));
}

export class InvalidTransition extends Error {}

/** Throw `InvalidTransition` if `from → to` is not allowed. */
export function validateTransition(from: string, to: string): void {
  if (!isValidStatus(to)) throw new InvalidTransition(`unknown status ${to}`);
  if (!canTransition(from, to)) throw new InvalidTransition(`illegal transition ${from} → ${to}`);
}
