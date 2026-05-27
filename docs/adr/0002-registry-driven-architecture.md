# ADR-002: Registry-driven Normalizer / Join / View architecture

**Status:** Accepted
**Date:** 2026-05

## Context

Hard-coded preprocessing wouldn't generalize past Graham; we expected to add sources, joins, and views faster than the core pipeline could absorb them.

## Decision

Three registries (Normalizer per source, Join per relationship, View per derived dataset), each populated via `@register_*` decorators imported by `scripts/preprocess/registry.py`.

## Consequences

Adding a source = one file in `normalizers/`. Adding a filter = one file in `views/`. The core pipeline doesn't change.
