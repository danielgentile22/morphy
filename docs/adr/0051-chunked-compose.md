# ADR-051: Chunked compose for memory-bounded large states

**Status:** Realized. Shipped 2026-05-19 (commit `f1141e4`); single-shot path retired 2026-05-27 (cleanup pass) — chunked is now the only compose path.
**Date:** 2026-05-20

## Context

The normalizer streams (ADR-050), but the original Composer did not. The single-shot `compose._load_state_data` loaded every county parquet for a state into memory and `pd.concat`'d them — measured at ~1,710 bytes/parcel, so ~19.5 GB peak for Florida's 11.18M parcels, far past the 16 GB dev machine. NC (~5.9M parcels) hit the same wall.

## Decision

Refactor the Composer to **chunk** parcels — process one shard at a time, run the parcel-touching joins against the small ancillary tables, and write per-shard composite slices (parcels become a multi-file layer, like the normalized layout). Globally-scoped joins/views (e.g. owner clustering) get a slim two-pass: pass 1 computes cluster IDs from an owner-columns-only projection of all parcels; pass 2 attaches them per shard. Peak memory stays bounded to a single shard.

## Consequences

FL and NC compose locally, as do future large states. The canonical schema and `catalog.json` contract are unchanged; the catalog advertises a `sharded: true` flag on the parcel layer. Small states (AR, MT) use the same path — one Composer = one bug surface. The legacy single-shot Composer was retired during the 2026-05-27 cleanup pass.
