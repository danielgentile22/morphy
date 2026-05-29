# ADR-001: Geographic scope is state-level, not county-level

**Status:** Accepted
**Date:** 2026-05 (v3 framework adoption)

## Context

The original Graham-County one-shot was county-specific. When generalizing, county-level composes would multiply outputs and make cross-state analytics awkward.

## Decision

The Composer runs per **state** (FIPS). County-level analysis is achieved via Views that filter a state composite by `county_fips`, not via a separate Composer mode.

## Consequences

State dropdown in the map; cross-county queries free; per-county refresh requires re-running the whole state.
