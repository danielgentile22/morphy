# ADR-041: No LLC unmasking (permanent non-goal)

**Status:** Narrowed by [ADR-057](0057-budget-posture-reframed.md) — paid skip-trace + shell-piercing remain permanent non-goals. Free public-records officer disclosure (Secretary of State business-entity lookups, UCC-1) is in scope for Phase 1 (Slice 4 D+E lead-detail panel).
**Date:** Carried forward from PROJECT_BRIEF

## Context

Resolving the human(s) behind an LLC is sensitive, expensive, and a separate product.

## Decision

Never implement in this repo. Display the raw entity string.

## Consequences

Pitch shows entity names as-is. Resolving people behind entities is a downstream business question, not ours.
