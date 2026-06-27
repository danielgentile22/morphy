# ADR-011: Anchor states locked: AR + NC + MT + UT (+ FL stretch)

**Status:** UT dropped by [ADR-049](0049-utah-dropped.md). Anchor set later re-cut by [ADR-060](0060-wv-committed-anchor.md) to the committed **AR + MT + FL + WV** (WV added; NC demoted to a deferred Phase-1 stretch).
**Date:** 2026-05-19

## Context

Free-data states with usable owner attribution.

## Decision

AR (confirmed great), NC (refresh from 11-month-stale data), MT (free cadastral), UT (small, clean). FL pursued only via new `fdor_nal` per-county tax-roll source (current FGDL DSL data is wrong dataset).

## Consequences

Pitch narrative is 4–5 states; not nationwide.
