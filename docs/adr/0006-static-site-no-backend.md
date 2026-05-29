# ADR-006: Static-site map app, no backend server

**Status:** Superseded by [ADR-055](0055-hosted-private-backend.md) for write-layer features (lead state, lease docs, auth). Read-only analytical layers (parquet, PMTiles, GeoJSON) stay static.
**Date:** 2026-05

## Context

A backend would simplify large-data queries but triples the deployment surface for a feasibility tool.

## Decision

The map app is a static JS bundle. All filtering / search runs in the browser (DuckDB-WASM over Parquet).

## Consequences

PMTiles + Parquet + GeoJSON over HTTP range requests need no backend. Puts a lower bound on map app complexity (the DuckDB-WASM bundle is ~6 MB).
