# ADR-023: `HUGE_GEOJSON_THRESHOLD = 100,000` rows

**Status:** Accepted
**Date:** 2026-05-18

## Context

AR (2.1M) and IN (3.7M) produced 3.6 GB / 5.6 GB parcel GeoJSONs that no browser can load.

## Decision

In `scripts/preprocess/io.py`, layers with ≥ 100K rows skip the full-geometry GeoJSON; only the simplified-geometry copy is written under `<layer>.geojson`.

## Consequences

Map app sees one geojson regardless; quality degrades smoothly. Parquet is canonical so analytics are unaffected.
