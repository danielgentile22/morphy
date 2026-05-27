# ADR-048: NC OneMap parcels: auto-fetch via MapServer pagination

**Status:** Accepted
**Date:** 2026-05-19

## Context

`nc_onemap_parcels` was wired to NC OneMap's Hub download API (`https://www.nconemap.gov/api/download/v1/items/<id>/shapefile`) which previously delivered the statewide shapefile bundle reliably. As of 2026-05 the endpoint returns persistent HTTP 500 across retries hours apart. A first pass flipped the source to MANUAL_ONLY, but the manual path required the user to split the 5.9M-record layer into ~6 batches via Hub's Download tab (Hub's async export ceiling is ~2M features) — wasting ~6 hours per refresh. The underlying ArcGIS MapServer `/query` endpoint is healthy and supports pagination at 5000 features/page.

## Decision

Keep `AutomationPolicy.ALLOWED`. Replace the broken bulk-API `fetch()` with a paginated MapServer query loop. Each page (5000 features, geometry @ EPSG:4326, ~21 explicit fields) is written as `page_NNNN.geojson` under `data/raw/nc_onemap_parcels/current/`. Resumable on interruption: pages already on disk are skipped. The normalizer reads them via rglob (already supports GeoJSON). The field map in `state_parcels.py` lists both casings (uppercase from legacy shapefile bulk, lowercase from MapServer JSON) for forward + back compat.

## Consequences

Fetch takes ~30–60 min unattended (1,186 sequential requests). Disk footprint: ~10 GB (vs ~2 GB for the old single-shapefile download — the per-page GeoJSON pages carry redundant FeatureCollection envelopes and verbose JSON encoding; acceptable trade-off for full automation). MapServer `/query` is the canonical ArcGIS REST endpoint, version-stable, and won't break with Hub UI redesigns. If NC restores the bulk-download API we can swap back to the simpler single-file path; the MapServer pagination remains as a documented fallback either way.
