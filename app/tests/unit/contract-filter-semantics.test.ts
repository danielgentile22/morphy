// Cross-language contract: owner filter semantics, TypeScript side (PRD #137).
//
// The FILTER_FIELDS registry projects each filter two ways from one definition:
// a DuckDB WHERE body (composeOwnerWhere) and a JS predicate (matchesOwner).
// This suite pins both against `contracts/filter_semantics.json`:
//   - composeOwnerWhere(filter) must equal the fixture's `where` (the generated
//     SQL is current — a generator change forces a fixture edit), and
//   - matchesOwner over the synthetic owners must select `expected_ids`.
// `tests/test_contract_filter_semantics.py` then executes that same `where` in a
// real DuckDB and asserts the same `expected_ids` — so SQL and predicate can't
// silently disagree.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  composeOwnerWhere,
  matchesOwner,
  emptyFilterModel,
  type FilterModel,
  type FilterableOwner,
} from '../../src/lib/filter-model';

interface FilterCase {
  name: string;
  filter: Partial<FilterModel>;
  where: string;
  expected_ids: string[];
}
interface FilterContract {
  owners: (FilterableOwner & { id: string })[];
  cases: FilterCase[];
}

const contract = JSON.parse(
  readFileSync(join(import.meta.dirname, '../../../contracts/filter_semantics.json'), 'utf-8'),
) as FilterContract;

describe('owner filter semantics contract (PRD #137)', () => {
  describe.each(contract.cases)('$name', (c: FilterCase) => {
    const model: FilterModel = { ...emptyFilterModel(), ...c.filter };

    it('composeOwnerWhere emits the fixture WHERE byte-for-byte', () => {
      expect(composeOwnerWhere(model)).toBe(c.where);
    });

    it('matchesOwner selects exactly expected_ids', () => {
      const got = contract.owners
        .filter((o) => matchesOwner(o, model))
        .map((o) => o.id)
        .sort();
      expect(got).toEqual([...c.expected_ids].sort());
    });
  });
});
