# ADR-043: Tests: pytest for backend; Vitest + Playwright deferred to map app v2

**Status:** Realized. The map app ships with Vitest unit + Playwright E2E tests in `app/tests/` (2026-05-21).
**Date:** 2026-05-19

## Context

Backend is Python; frontend rebuild is deferred.

## Decision

Add pytest now for `scripts/preprocess/` + fixtures. Vitest + Playwright wait until the map app v2 work begins.

## Consequences

Backend regression coverage is the immediate priority; UI tests follow the rebuild.
