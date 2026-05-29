# ADR-004: Current-only data versioning, no history

**Status:** Accepted
**Date:** 2026-05 (user-confirmed during puller design)

## Context

Retaining every prior raw download would balloon disk use (~15 GB per snapshot today, more as we add states); incremental diffing isn't needed for a feasibility prototype.

## Decision

`data/raw/<source_id>/current/` is the only state retained. Re-pulls overwrite. Audit trail lives in `data/fetch.log`.

## Consequences

Can't time-travel ("what did parcels look like 6 months ago?"). Acceptable for a pitch cut; revisit if commercial use requires audit trail.
