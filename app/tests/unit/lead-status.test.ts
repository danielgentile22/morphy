import { describe, it, expect } from 'vitest';
import {
  STATUSES,
  INITIAL_STATUS,
  TERMINAL_STATUSES,
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

  it('treats terminal statuses as terminal', () => {
    expect([...TERMINAL_STATUSES].sort()).toEqual(['in_business', 'uninterested']);
    for (const s of STATUSES) {
      expect(canTransition('uninterested', s === 'uninterested' ? s : s)).toBe(s === 'uninterested');
      expect(canTransition('in_business', s === 'in_business' ? s : s)).toBe(s === 'in_business');
    }
  });

  it('nextStatuses lists the current status plus legal moves, in ladder order', () => {
    expect(nextStatuses('new')).toEqual(['new', 'researching']);
    expect(nextStatuses('contacted')).toEqual(['contacted', 'interested', 'uninterested']);
    expect(nextStatuses('uninterested')).toEqual(['uninterested']);
  });

  it('validateTransition throws InvalidTransition on an illegal move', () => {
    expect(() => validateTransition('new', 'researching')).not.toThrow();
    expect(() => validateTransition('new', 'in_business')).toThrow(InvalidTransition);
    expect(() => validateTransition('new', 'bogus')).toThrow(InvalidTransition);
  });
});
