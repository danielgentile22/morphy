# ADR-005: On-demand fetch trigger only

**Status:** Accepted
**Date:** 2026-05

## Context

Scheduled background daemons add operational burden for a solo-dev prototype.

## Decision

All raw pulls are manually triggered via the puller UI. No cron, no in-app schedulers.

## Consequences

The puller must surface staleness clearly (see [DATA_FRESHNESS.md](../DATA_FRESHNESS.md)) so the user doesn't forget. Cadence-aware notification was never built.
