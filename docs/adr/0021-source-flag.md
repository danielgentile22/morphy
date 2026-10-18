# ADR-021: `--source` flag for selective rebuild

**Status:** Accepted
**Date:** 2026-05-19

## Context

Force-rebuild currently re-normalizes everything; for a single-source fix, this wastes 30+ min.

## Decision

`python scripts/preprocess.py --source <id>` runs one source through the normal manifest-aware path. No bypass.

## Consequences

Eliminates the manifest-bypass problem that had left the manifest stale.
