# ADR-052: `NO_GEOJSON_THRESHOLD`: Parquet-only for very large layers

**Status:** Accepted
**Date:** 2026-05-21

## Context

`io.py` had a single `HUGE_GEOJSON_THRESHOLD` (100K rows) that switched a layer from a *full* to a *simplified* GeoJSON. The logic assumed "simplified ⇒ browser-safe", which is false past a few hundred thousand polygons: AR's 2.1M-parcel simplified `parcels.geojson` was **3.9 GB** and MT's **1.8 GB** — unloadable in any browser. The audit flagged this as a P0 blocker.

## Decision

Add a hard ceiling `NO_GEOJSON_THRESHOLD` (250,000 rows). At or above it, `dual_write_spatial` writes **Parquet only** — no full and no simplified GeoJSON. `catalog.json` advertises a `geojson_path` only when the file actually exists on disk. The map app needs no all-parcels GeoJSON — it renders every parcel from PMTiles vector tiles (built from the Parquet), and the per-state Views as GeoJSON.

## Consequences

AR/MT composites no longer carry a multi-GB `parcels.geojson` (~5.7 GB disk reclaimed). Parquet stays the canonical analytical format. Towers, solar, distress overlays and every View sit well under the ceiling and keep their GeoJSON. No change to the catalog contract beyond paths now being existence-gated.
