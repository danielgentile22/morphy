// Contact-attempt form options + payload mapping (Slice 3 / #49).
//
// Kept as pure logic (no Svelte, no fetch) so the form → API-payload
// mapping is unit-testable in isolation; the LeadPage form binds to these.

import type { ActivityDirection, AttemptPayload } from './leads-api';

/** Outreach channels a manual attempt can use (best_channel shares these). */
export const CHANNELS = ['phone', 'mail', 'email', 'text', 'in-person'] as const;
export type Channel = (typeof CHANNELS)[number];

/** Outcomes for a logged attempt. */
export const OUTCOMES = [
  'no answer',
  'left voicemail',
  'bad number',
  'spoke – interested',
  'spoke – not interested',
  'sent',
  'returned',
  'meeting',
] as const;
export type Outcome = (typeof OUTCOMES)[number];

/** Outcomes for a logged *reply* (an inbound event, #106) — what the owner
 *  said back, not what we did. */
export const REPLY_OUTCOMES = [
  'interested',
  'not interested',
  'asked for info',
  'asked to call back',
  'wrong owner',
  'other',
] as const;
export type ReplyOutcome = (typeof REPLY_OUTCOMES)[number];

export interface AttemptForm {
  channel: string;
  outcome: string;
  note?: string;
  /** ISO date (yyyy-mm-dd); empty/absent → backend defaults to today. */
  occurred_on?: string;
}

/** Map the attempt form to the exact backend POST body. Trims text and
 *  normalises an empty date to `null` (server stamps today). ``direction``
 *  defaults to outbound (a touch); pass `'inbound'` to log a reply (#106) —
 *  the key is omitted when outbound so the body stays minimal (the server
 *  defaults it). */
export function buildAttemptPayload(
  form: AttemptForm,
  direction: ActivityDirection = 'outbound',
): AttemptPayload {
  const occurred = (form.occurred_on ?? '').trim();
  const payload: AttemptPayload = {
    channel: form.channel.trim(),
    outcome: form.outcome.trim(),
    note: (form.note ?? '').trim(),
    occurred_on: occurred === '' ? null : occurred,
  };
  if (direction === 'inbound') payload.direction = 'inbound';
  return payload;
}
