<!-- See docs/TESTING.md for the rules referenced below. -->

## Summary

<!-- 1-3 sentences. What and why. -->

## Decisions

- [ ] If this touches a locked decision in `docs/DECISIONS.md`, the PR
      either adds a new ADR or amends an existing one

## Tests

- [ ] Existing tests pass locally (`pytest`)
- [ ] New tests added for new logic (per `docs/TESTING.md`)
- [ ] If this touches a normalizer / join / view, fixture-based test
      covers the change

## Docs

- [ ] Affected docs (e.g. DATA_SOURCES.md, LIMITATIONS.md) reflect the change

## Risk + reversibility

<!--
How risky is this change? What's the rollback path?
- One-liner config tweak, trivial revert
- Schema bump; downstream code needs adjustment if reverted
- Data ingest change; affects future preprocess runs
-->

## PII / security

- [ ] No `data/` or composite outputs committed
- [ ] No secrets / API keys / credentials in the diff
- [ ] If this changes how owner personally identifiable information (PII) is stored or surfaced, `docs/SECURITY.md` updated
