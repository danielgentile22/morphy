# ADR-015: HIFLD towers retired

**Status:** Accepted
**Date:** 2026-05-19

## Context

DHS retired the public HIFLD cellular-towers layer in 2024 as part of an infrastructure-data security review.

## Decision

Mark RETIRED in registry. Do not attempt to re-fetch.

## Consequences

FCC ASR is now the sole tower-locations source. Some short / rooftop towers won't appear (ASR's ≥ 200 ft threshold).
