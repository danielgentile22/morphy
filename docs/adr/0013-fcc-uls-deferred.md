# ADR-013: FCC ULS normalizers deferred to post-pitch

**Status:** Partially reversed by [ADR-053](0053-product-phase-shift.md) Slice A — Cellular (Part 22) + PCS (Part 24) + AWS / 700 MHz (Part 27) bands are in Phase 1 for carrier identification. Microwave, Ownership, Transfers, Leasing remain deferred to Slice B / Phase 2.
**Date:** 2026-05-19

## Context

~5 GB of raw ULS data on disk across 6 bands + meta; complex per-band schema; landowner-side pitch doesn't depend on carrier tenancy data.

## Decision

Leave raw data on disk; mark sources as deferred in the registry; no normalizers built this cut.

## Consequences

Carrier-presence per tower is a v2 enhancement. Lease-economic modeling waits.
