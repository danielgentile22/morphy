import { describe, it, expect } from 'vitest';
import {
  STATUSES,
  INITIAL_STATUS,
  TERMINAL_STATUSES,
  KANBAN_LANES,
  canTransition,
  nextStatuses,
  isValidStatus,
  validateTransition,
  InvalidTransition,
} from '../../src/lib/lead-status';

describe('lead status ladder', () => {
  it('defaults to New', () => {
    expect(INITIAL_STATUS).toBe('new');
  });

  it('knows the six statuses and rejects unknowns', () => {
    expect(STATUSES).toEqual([
      'new',
      'researching',
      'contacted',
      'interested',
      'in_business',
      'uninterested',
    ]);
    expect(isValidStatus('new')).toBe(true);
    expect(isValidStatus('flagged')).toBe(false);
  });

  it('allows each legal forward step', () => {
    expect(canTransition('new', 'researching')).toBe(true);
    expect(canTransition('researching', 'contacted')).toBe(true);
    expect(canTransition('contacted', 'interested')).toBe(true);
    expect(canTransition('interested', 'in_business')).toBe(true);
  });

  it('allows the give-up branch to Uninterested after work has started', () => {
    expect(canTransition('researching', 'uninterested')).toBe(true);
    expect(canTransition('contacted', 'uninterested')).toBe(true);
    expect(canTransition('interested', 'uninterested')).toBe(true);
  });

  it('allows re-saving the same status (idempotent note save)', () => {
    for (const s of STATUSES) expect(canTransition(s, s)).toBe(true);
  });

  it('rejects skipping rungs', () => {
    expect(canTransition('new', 'in_business')).toBe(false); // the headline illegal case
    expect(canTransition('new', 'contacted')).toBe(false);
    expect(canTransition('contacted', 'in_business')).toBe(false); // only via interested
    expect(canTransition('new', 'uninterested')).toBe(false);
  });

  it('makes In Business reachable only via Interested', () => {
    expect(canTransition('interested', 'in_business')).toBe(true);
    for (const s of ['new', 'researching', 'contacted'] as const) {
      expect(canTransition(s, 'in_business')).toBe(false);
    }
  });

  it('marks in_business + uninterested as closed lanes, but only in_business is transition-locked', () => {
    expect([...TERMINAL_STATUSES].sort()).toEqual(['in_business', 'uninterested']);
    // in_business (won) is the one true terminal — no outgoing move but the identity save.
    for (const s of STATUSES) {
      expect(canTransition('in_business', s)).toBe(s === 'in_business');
    }
  });

  it('reopens Uninterested to any status (a lost/parked lead is never stranded)', () => {
    for (const s of STATUSES) {
      expect(canTransition('uninterested', s)).toBe(true); // every status incl. the identity save
    }
  });

  it('nextStatuses lists the current status plus legal moves, in ladder order', () => {
    expect(nextStatuses('new')).toEqual(['new', 'researching']);
    expect(nextStatuses('contacted')).toEqual(['contacted', 'interested', 'uninterested']);
    // Uninterested can reopen anywhere → its whole ladder, in order.
    expect(nextStatuses('uninterested')).toEqual([
      'new',
      'researching',
      'contacted',
      'interested',
      'in_business',
      'uninterested',
    ]);
  });

  it('validateTransition throws InvalidTransition on an illegal move', () => {
    expect(() => validateTransition('new', 'researching')).not.toThrow();
    expect(() => validateTransition('new', 'in_business')).toThrow(InvalidTransition);
    expect(() => validateTransition('new', 'bogus')).toThrow(InvalidTransition);
  });
});

// The My-Leads kanban (Slice 5 / #51) drives status changes by dragging a
// card between lanes. The lanes are exactly the non-New statuses, and a drop
// is just a transition validated by the same ladder above.
describe('kanban lanes + drag transitions', () => {
  it('has one lane per status except New, in ladder order', () => {
    expect(KANBAN_LANES).toEqual([
      'researching',
      'contacted',
      'interested',
      'in_business',
      'uninterested',
    ]);
    expect(KANBAN_LANES).not.toContain(INITIAL_STATUS); // New lives in Candidates
  });

  it('allows dragging forward one lane at a time', () => {
    expect(canTransition('researching', 'contacted')).toBe(true);
    expect(canTransition('contacted', 'interested')).toBe(true);
    expect(canTransition('interested', 'in_business')).toBe(true);
  });

  it('allows dragging any worked lane into the closed Uninterested lane', () => {
    for (const lane of ['researching', 'contacted', 'interested'] as const) {
      expect(canTransition(lane, 'uninterested')).toBe(true);
    }
  });

  it('rejects dragging a Contacted card straight into In Business', () => {
    // The headline illegal drop from the issue — only reachable via Interested.
    expect(canTransition('contacted', 'in_business')).toBe(false);
  });

  it('rejects dragging backward on the active ladder + out of the won lane', () => {
    expect(canTransition('contacted', 'researching')).toBe(false);
    expect(canTransition('interested', 'contacted')).toBe(false);
    expect(canTransition('in_business', 'interested')).toBe(false); // won is locked
  });

  it('allows dragging a card back out of the Uninterested lane (reopen)', () => {
    expect(canTransition('uninterested', 'researching')).toBe(true);
    expect(canTransition('uninterested', 'contacted')).toBe(true);
  });
});
