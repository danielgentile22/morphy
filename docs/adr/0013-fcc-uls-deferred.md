# ADR-013: FCC ULS normalizers deferred past the first cut

**Status:** Partially reversed by [ADR-053](0053-product-phase-shift.md) Slice A. Cellular (Part 22), PCS (Personal Communications Service, Part 24) and AWS (Advanced Wireless Services) / 700 MHz (Part 27) bands came into Phase 1 for carrier identification. Microwave, Ownership, Transfers and Leasing stayed deferred to Slice B / Phase 2.
**Date:** 2026-05-19

## Context

~5 GB of raw Federal Communications Commission (FCC) Universal Licensing System (ULS) data on disk across 6 bands + meta; complex per-band schema; the landowner-side analysis didn't depend on carrier tenancy data.

## Decision

Leave raw data on disk; mark sources as deferred in the registry; no normalizers built this cut.

## Consequences

Carrier presence per tower was left for v2, and lease-economic modeling waited with it.
