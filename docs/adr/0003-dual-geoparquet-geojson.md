# ADR-003: Dual GeoParquet + GeoJSON output

**Status:** Accepted
**Date:** 2026-05

## Context

Parquet is dramatically smaller, supports column projection, and is the right analytical format. But the legacy Leaflet app only speaks GeoJSON.

## Decision

Every spatial output is written as both `<layer>.parquet` (canonical) and `<layer>.geojson` (for the map). For layers ≥ `HUGE_GEOJSON_THRESHOLD` (100K rows) only the simplified-geometry GeoJSON is written.

## Consequences

Doubles disk usage for small layers. The shipped map app (ADR-030) reads the GeoJSON for its catalog layers; the parcel layer uses PMTiles built from the Parquet.
