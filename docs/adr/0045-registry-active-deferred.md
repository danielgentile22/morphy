# ADR-045: Registry split: `_ACTIVE` + `_DEFERRED` blocks

**Status:** Accepted
**Date:** 2026-05-19

## Context

Section 4.3 reduced the v1 surface to ~14 sources but the original `scripts/fetch/registry.py` had no way to track "imported but not in v1 scope" classes. Deleting them would erase the schema work; comment-blocks rot.

## Decision

Registry exposes two lists — `_ACTIVE` (shown to the puller and preprocess) and `_DEFERRED` (imported but invisible upstream). `all_sources()` returns only active; `deferred_sources()` exists for tooling. `get_source()` resolves across both so a reactivated source keeps working with the same ID.

## Consequences

Reactivating any deferred source = one-line move between the lists. Puller's `_prune_orphan_manifest_entries` cleans the manifest automatically when something moves from active to deferred.
