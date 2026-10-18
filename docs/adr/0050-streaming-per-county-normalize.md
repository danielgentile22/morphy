# ADR-050: Streaming per-county parcel normalize

**Status:** Accepted
**Date:** 2026-05-20

## Context

The parcel normalizer originally read every layer of a multi-layer source, materialised them all in memory, and concatenated before mapping to canonical. Fine for single-layer sources (AR), but Florida's FDOR set is 67 county shapefiles totalling ~28 GB raw. Concatenating them would need ~50 GB peak RAM, far past the 16 GB dev machine. The old code also had a silent "fall back to all layers" path that, combined with a wrong MT field map, concatenated 12 unrelated Montana shapefiles into one garbage 6.5M-row output.

## Decision

The normalizer **streams**. It processes one county-layer at a time, maps it to canonical, and writes one parquet per county under `normalized/<source>/<canonical_type>/<county>.parquet`, with the raw copy under `normalized/<source>/raw/<county>.parquet`. Peak memory is bounded to a single county. Normalize-stage GeoJSON output is dropped (GeoParquet only); the Composer still dual-writes GeoParquet + GeoJSON for the map app (ADR-003). The Composer's loader reads the per-county parquet directory transparently. The silent layer-fallback was removed and replaced with a loud `RuntimeError`.

## Consequences

FL's 11.2M-parcel set normalizes within memory. AR's re-normalize got *faster and smaller* (~2m29s, 1.3 GB output) because the redundant GeoJSON write is gone. The MT garbage-output failure mode is now impossible. A missing expected layer fails loudly instead of silently widening scope.
