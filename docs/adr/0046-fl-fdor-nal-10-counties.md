# ADR-046: FL parcel data: replace FGDL DSL with FDOR NAL

**Status:** Superseded by [ADR-047](0047-fdor-nal-67-counties.md) (county set expanded from 10 to all 67).
**Date:** 2026-05-19

## Context

The previously-active `fl_fgdl_parcels` source pulls FGDL DSL (state-domain land, meaning state-owned parcels) which has no private-landowner data. Composing FL with that produced empty `owner_name` columns and was useless for owner analysis.

## Decision

New source `fdor_nal` (Florida Department of Revenue Name-Address-Legal tax roll, per-county). MANUAL_ONLY with a per-county walkthrough; v1 originally shipped 10 representative counties (~60% of FL population): Miami-Dade, Hillsborough, Orange, Duval, Pinellas, Lee, Polk, Brevard, Volusia, Marion.

## Consequences

FL composite gains owner data. FGDL DSL moved to deferred.
