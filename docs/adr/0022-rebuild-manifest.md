# ADR-022: `--rebuild-manifest` for disk-derived sync

**Status:** Accepted
**Date:** 2026-05-19

## Context

The preprocess manifest can drift from disk reality when work is interrupted or paths are touched outside the runner.

## Decision

`python scripts/preprocess.py --rebuild-manifest` walks `data/processed/normalized/*/` + `data/processed/composite/*/` and rewrites the manifest from current files. Does not re-run preprocessing.

## Consequences

Cheap recovery path, worth running after any non-trivial work session.
