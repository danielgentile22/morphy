// Cross-language contract: the Lead status ladder, TypeScript side (PRD #137).
//
// Asserts `app/src/lib/lead-status.ts` against `contracts/lead_status_ladder.json`
// — the same language-neutral fixture the backend's pytest suite asserts
// `backend/app/lead_status.py` against (`backend/tests/test_contract_lead_status.py`).
// If the ladder drifts on one side, that side's suite goes red against this fixture.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  STATUSES,
  INITIAL_STATUS,
  TERMINAL_STATUSES,
  canTransition,
  validateTransition,
  InvalidTransition,
} from '../../src/lib/lead-status';

interface TransitionCase {
  from: string;
  to: string;
  allowed: boolean;
  note?: string;
}
interface LadderContract {
  statuses: string[];
  initial_status: string;
  terminal_statuses: string[];
  allowed_transitions: Record<string, string[]>;
  transition_cases: TransitionCase[];
}

const contract = JSON.parse(
  readFileSync(join(import.meta.dirname, '../../../contracts/lead_status_ladder.json'), 'utf-8'),
) as LadderContract;

describe('lead-status ladder contract (PRD #137)', () => {
  it('status set / initial / terminal match the contract', () => {
    expect([...STATUSES]).toEqual(contract.statuses);
    expect(INITIAL_STATUS).toBe(contract.initial_status);
    expect([...TERMINAL_STATUSES].sort()).toEqual([...contract.terminal_statuses].sort());
  });

  it('the allowed-transitions table matches the contract', () => {
    // ALLOWED_TRANSITIONS is module-private; derive each from-status's forward
    // set from the public canTransition (excluding the always-legal identity).
    for (const from of contract.statuses) {
      const forward = contract.statuses
        .filter((to) => to !== from && canTransition(from, to))
        .sort();
      expect(forward).toEqual([...contract.allowed_transitions[from]].sort());
    }
  });

  describe.each(contract.transition_cases)('$from -> $to', (c: TransitionCase) => {
    it(`canTransition is ${c.allowed}`, () => {
      expect(canTransition(c.from, c.to)).toBe(c.allowed);
    });

    it(`validateTransition ${c.allowed ? 'does not throw' : 'throws'}`, () => {
      if (c.allowed) {
        expect(() => validateTransition(c.from, c.to)).not.toThrow();
      } else {
        expect(() => validateTransition(c.from, c.to)).toThrow(InvalidTransition);
      }
    });
  });
});
