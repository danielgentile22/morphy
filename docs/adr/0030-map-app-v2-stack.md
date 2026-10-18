# ADR-030: Map app v2 stack: MapLibre + PMTiles + DuckDB-WASM + Svelte

**Status:** Realized. Shipped 2026-05-21. See [../../app/ARCHITECTURE.md](../../app/ARCHITECTURE.md).
**Date:** 2026-05-19

## Context

The current Leaflet app can't handle multi-million-parcel states; filter surface lags v3 schema fields.

## Decision

v2 uses MapLibre GL JS (WebGL rendering), PMTiles (single-file vector tiles, no server), DuckDB-WASM (in-browser SQL over Parquet via HTTP range requests), Svelte + Vite (UI). Tippecanoe generates PMTiles at preprocess time.

## Consequences

Adds Node toolchain + Homebrew tippecanoe to developer requirements. Static-site model preserved (ADR-006).
