# ADR-019: FL FGDL DSL parcels replaced by `fdor_nal` source

**Status:** Superseded by [ADR-047](0047-fdor-nal-67-counties.md) — the `fdor_nal` source this ADR introduced was expanded from a county subset to all 67 FL counties; that ADR is the live FL-parcels decision. The FGDL → FDOR NAL switch itself stands.
**Date:** 2026-05-19

## Context

The currently-installed FL parcel data is FGDL's Department of State Lands (DSL) layer — publicly-owned state land only, not the FDOR NAL tax roll with private owners.

## Decision

Drop FGDL from active registry. Add a new `scripts/fetch/sources/fdor_nal.py` source for the FDOR NAL data, policy MANUAL_ONLY (per-county downloads).

## Consequences

FL anchor depends on user pulling 5–10 representative counties (Miami-Dade, Hillsborough, Orange, Duval, Pinellas, Lee, Polk, Brevard, Volusia, Marion suggested).
