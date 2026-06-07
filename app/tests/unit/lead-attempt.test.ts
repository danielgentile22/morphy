import { describe, it, expect } from 'vitest';
import {
  CHANNELS,
  OUTCOMES,
  REPLY_OUTCOMES,
  buildAttemptPayload,
} from '../../src/lib/lead-attempt';

describe('contact-attempt form → API payload', () => {
  it('maps a filled form to the POST body verbatim (trimmed)', () => {
    expect(
      buildAttemptPayload({
        channel: 'phone',
        outcome: 'left voicemail',
        note: '  called twice  ',
        occurred_on: '2026-05-30',
      }),
    ).toEqual({
      channel: 'phone',
      outcome: 'left voicemail',
      note: 'called twice',
      occurred_on: '2026-05-30',
    });
  });

  it('normalises an empty/absent date to null (server stamps today)', () => {
    expect(buildAttemptPayload({ channel: 'mail', outcome: 'sent' }).occurred_on).toBeNull();
    expect(
      buildAttemptPayload({ channel: 'mail', outcome: 'sent', occurred_on: '   ' }).occurred_on,
    ).toBeNull();
  });

  it('defaults note to an empty string when absent', () => {
    expect(buildAttemptPayload({ channel: 'email', outcome: 'sent' }).note).toBe('');
  });

  it('exposes the channel + outcome option lists the form binds to', () => {
    expect(CHANNELS).toContain('phone');
    expect(CHANNELS).toContain('in-person');
    expect(OUTCOMES).toContain('no answer');
    expect(OUTCOMES.length).toBeGreaterThan(3);
  });

  // ── inbound replies (#106, ADR-066) ────────────────────────────────────────
  it('omits direction for an outbound touch (server defaults it)', () => {
    expect(buildAttemptPayload({ channel: 'phone', outcome: 'sent' })).not.toHaveProperty(
      'direction',
    );
    expect(
      buildAttemptPayload({ channel: 'phone', outcome: 'sent' }, 'outbound'),
    ).not.toHaveProperty('direction');
  });

  it('marks an inbound reply with direction=inbound', () => {
    expect(
      buildAttemptPayload({ channel: 'email', outcome: 'interested' }, 'inbound'),
    ).toEqual({
      channel: 'email',
      outcome: 'interested',
      note: '',
      occurred_on: null,
      direction: 'inbound',
    });
  });

  it('exposes reply outcomes distinct from outbound outcomes', () => {
    expect(REPLY_OUTCOMES).toContain('interested');
    expect(REPLY_OUTCOMES).toContain('asked to call back');
  });
});
