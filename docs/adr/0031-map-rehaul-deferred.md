# ADR-031: Map app rehaul deferred past the first cut

**Status:** Superseded. The rehaul happened within this cut as Section 8 (2026-05-21) instead of being deferred. See [ADR-030](0030-map-app-v2-stack.md).
**Date:** 2026-05-19

## Context

Audit found bigger gaps (broken endpoints, missing normalizers, no tests, doc drift) than the map app itself. Sequencing them first builds a solid foundation for the rebuild.

## Decision

v1 Leaflet app gets minimal patches only during this cut (Section 8 of the work plan). Full rebuild waits until after the first cut.

## Consequences

Demos use the current map. Map performance caveats live in LIMITATIONS.md.
