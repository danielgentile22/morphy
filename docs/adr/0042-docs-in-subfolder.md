# ADR-042: Documentation lives in `docs/` (subfolder)

**Status:** Accepted
**Date:** 2026-05-19

## Context

Root had 7 .md files with ~3500 lines mixing business, technical, plan, and limitations. Cognitively overloading.

## Decision

Root keeps only README.md, CLAUDE.md, PROJECT_BRIEF.md. All other docs move to `docs/`. New docs go straight to `docs/`.

## Consequences

Root stays scannable. Inbound links from README/CLAUDE point into `docs/`.
