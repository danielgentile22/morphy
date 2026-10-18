# Cross-language contract fixtures

Two domain contracts live in two languages each, kept in sync by nothing but
discipline:

- the **Lead status ladder**, implemented in Python (`backend/app/lead_status.py`)
  and TypeScript (`app/src/lib/lead-status.ts`);
- **owner filter semantics**, one `FILTER_FIELDS` registry
  (`app/src/lib/filter-model.ts`) projected two ways: a DuckDB SQL `WHERE` body
  (`composeOwnerWhere`) and a JS runtime predicate (`matchesOwner`).

When one side moves and the other doesn't, the failure is silent and
user-facing (a transition the backend rejects but the UI offers; a filter that
matches different sets in the map and the owner list). This directory makes each
contract a **language-neutral JSON fixture asserted by both sides' test suites**
The fixture is the contract: divergence becomes a red test on the side that
moved. No codegen, no shared runtime; just the same examples asserted
twice.

## Files

| Fixture | What it pins |
|---|---|
| `lead_status_ladder.json` | statuses, initial/terminal sets, the allowed-transitions table, and `(from, to, allowed?)` cases (all 36 pairs + unknown-status edges) |
| `filter_semantics.json` | a synthetic owner dataset (typed by `owner_columns`) + filter cases, each carrying the generated `where` and the `expected_ids` both engines must reproduce |

## Who consumes each (all in the normal CI gates)

| Fixture | Backend (pytest gate) | Frontend (vitest gate) |
|---|---|---|
| `lead_status_ladder.json` | `backend/tests/test_contract_lead_status.py` asserts the Python validator | `app/tests/unit/contract-lead-status.test.ts` asserts the TS mirror |
| `filter_semantics.json` | `tests/test_contract_filter_semantics.py` **executes** each `where` in in-process DuckDB | `app/tests/unit/contract-filter-semantics.test.ts` asserts `composeOwnerWhere` output + the `matchesOwner` predicate |

The filter contract's SQL is executed in **Python's native DuckDB**, not in the
browser: DuckDB-WASM can't run under Vitest (the suite stubs `Worker` to a no-op
so the module merely imports), whereas `duckdb` is already a pipeline/test
dependency and runs fast and stably in the pytest gate. Vitest asserts the
generated `where` string byte-for-byte, so it can never go stale relative to the
generator; pytest runs that exact string. Both gates run on every PR, so
cross-language drift fails the PR that caused it, with no reliance on the e2e
suite (which needs multi-GB composites and is out of the PR gate).

## Extending

- **A new status / transition rule:** edit `lead_status_ladder.json` (the
  `statuses`, `allowed_transitions`, and `transition_cases`). Both suites
  re-derive from it; the side that hasn't been updated goes red.
- **A new filter field / case:** add the field to `owner_columns` and to every
  `owners` row, then add cases. Regenerate `where`/`expected_ids` by running the
  real implementations (do **not** hand-author them blind), and confirm both
  engines agree before committing. If they don't, that's a bug to file, not a
  fixture to fudge.
- Fixture edits are reviewed like API changes: they **are** the contract.

## Scope notes

- The parcel filter registry (`app/src/lib/filters.ts`) is SQL-only (it has no
  JS predicate counterpart), so it is deliberately **not** part of the
  two-engine parity fixture here.
- These fixtures encode the behavior as it stood when the project was archived.
  Changing a status rule or filter semantic is a separate change; this is the
  regression net that makes such a change show up on both sides at once.
