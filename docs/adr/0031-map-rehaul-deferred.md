# ADR-031: Map app rehaul deferred to post-pitch

**Status:** Superseded — the rehaul was executed within this cut as Section 8 (2026-05-21), not deferred to post-pitch. See [ADR-030](0030-map-app-v2-stack.md).
**Date:** 2026-05-19

## Context

Audit found bigger gaps (broken endpoints, missing normalizers, no tests, doc drift) than the map app itself. Sequencing them first builds a solid foundation for the rebuild.

## Decision

v1 Leaflet app gets minimal patches only during this cut (Section 8 of the work plan). Full rebuild starts after the pitch lands.

## Consequences

Pitch demos use the current map. Map performance caveats live in LIMITATIONS.md.
