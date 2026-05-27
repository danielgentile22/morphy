# ADR-051: Chunked compose for memory-bounded large states

**Status:** Approved; **not yet implemented** as of 2026-05-20.
**Date:** 2026-05-20

## Context

The normalizer streams (ADR-050), but the **Composer** does not. `compose._load_state_data` loads every county parquet for a state into memory and `pd.concat`s them — measured at ~1,710 bytes/parcel, so ~19.5 GB peak for Florida's 11.18M parcels, far past the 16 GB dev machine. A local FL compose this session ran through the load and all 9 joins (macOS swaps rather than OOM-killing) but the ~13 GB `parcels.parquet` write exhausted the near-full disk. NC (~5.9M parcels) will hit the same wall.

## Decision

Refactor the Composer to **chunk** parcels — process one county at a time, run the parcel-touching joins against the small ancillary tables, and write per-county composite slices (parcels become a multi-file layer, like the normalized layout). Globally-scoped joins/views (e.g. owner clustering) get a slim two-pass: pass 1 computes cluster IDs from an owner-columns-only projection of all parcels; pass 2 attaches them per county. Peak memory stays bounded to a single county.

## Consequences

FL and NC compose locally, as will future large states. The Composer plus the global joins/views need the refactor and tests. No change to the canonical schema or the `catalog.json` contract. Small single-layer states (AR, MT) are unaffected.
