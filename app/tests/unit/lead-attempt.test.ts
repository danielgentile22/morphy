import { describe, it, expect } from 'vitest';
import { CHANNELS, OUTCOMES, buildAttemptPayload } from '../../src/lib/lead-attempt';

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
});
