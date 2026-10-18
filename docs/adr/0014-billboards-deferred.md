# ADR-014: Billboards deferred

**Status:** Partially reversed by [ADR-053](0053-product-phase-shift.md) Slice C. Billboards ran as **parcel enrichment** (`has_billboard`, `billboard_count`) in Phase 1, not as a primary triage axis. Billboards as a primary asset class stayed deferred to Phase 3.
**Date:** 2026-05-19

## Context

Three state Department of Transportation (DOT) billboard sources are in the registry; not core to the cell-tower thesis.

## Decision

Defer billboard normalizers past the first cut.

## Consequences

The first cut covered cell towers only.
