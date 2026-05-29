# ADR-044: CI on GitHub Actions

**Status:** Accepted
**Date:** 2026-05-19

## Context

User confirmed GitHub as the version-control home.

## Decision

`.github/workflows/lint.yml` (ruff) and `.github/workflows/test.yml` (pytest) on every push.

## Consequences

All pushes must pass lint + tests once Section 6 lands. Branch protection follows.
