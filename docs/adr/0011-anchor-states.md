# ADR-011: Anchor states locked: AR + NC + MT + UT (+ FL stretch)

**Status:** UT dropped by [ADR-049](0049-utah-dropped.md). Anchor set later re-cut by [ADR-060](0060-wv-committed-anchor.md) to the committed **AR + MT + FL + WV** (WV added; NC demoted to a deferred Phase-1 stretch).
**Date:** 2026-05-19

## Context

Free-data states with usable owner attribution.

## Decision

Arkansas (AR, confirmed great), North Carolina (NC, refresh from 11-month-stale data), Montana (MT, free cadastral), Utah (UT, small, clean). Florida (FL) pursued only via a new `fdor_nal` per-county tax-roll source, because the installed FGDL (Florida Geographic Data Library) DSL data was the wrong dataset.

## Consequences

Phase 1 covered 4-5 states, not the whole country.
