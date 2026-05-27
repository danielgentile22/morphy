# ADR-007: PySide6 pinned at 6.7.3

**Status:** Accepted
**Date:** 2026-05

## Context

PySide6 6.11.x had a cocoa-plugin load failure on the developer's macOS arm64 setup.

## Decision

Pin `PySide6 == 6.7.3` (long-term-support branch).

## Consequences

Don't `pip install --upgrade` casually. Re-evaluate if 6.7.x reaches EOL.
