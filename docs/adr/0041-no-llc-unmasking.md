# ADR-041: No LLC unmasking (permanent non-goal)

**Status:** Narrowed by [ADR-057](0057-budget-posture-reframed.md). Paid skip-trace and shell-piercing remained permanent non-goals. Free public-records officer disclosure (Secretary of State business-entity lookups, Uniform Commercial Code UCC-1 financing statements) was in scope for Phase 1 (Slice 4 D+E lead-detail panel).
**Date:** Carried forward from the original project brief

## Context

Resolving the human(s) behind an LLC is sensitive, expensive, and a separate product.

## Decision

Never implement in this repo. Display the raw entity string.

## Consequences

The app shows entity names as-is. Resolving the people behind entities is out of scope for this repo.
