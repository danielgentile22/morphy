# ADR-019: FL FGDL DSL parcels replaced by `fdor_nal` source

**Status:** Superseded by [ADR-047](0047-fdor-nal-67-counties.md). The `fdor_nal` source this ADR introduced grew from a county subset to all 67 FL counties, and that ADR holds the FL-parcels decision. The FGDL → FDOR NAL switch itself stands.
**Date:** 2026-05-19

## Context

The installed FL parcel data was the Florida Geographic Data Library (FGDL) Division of State Lands (DSL) layer. It covers publicly-owned state land only, not the Florida Department of Revenue (FDOR) Name-Address-Legal (NAL) tax roll with private owners.

## Decision

Drop FGDL from active registry. Add a new `scripts/fetch/sources/fdor_nal.py` source for the FDOR NAL data, policy MANUAL_ONLY (per-county downloads).

## Consequences

The FL anchor depended on the user pulling 5-10 representative counties (Miami-Dade, Hillsborough, Orange, Duval, Pinellas, Lee, Polk, Brevard, Volusia, Marion suggested).
