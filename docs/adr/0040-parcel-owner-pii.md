# ADR-040: Parcel-owner data is PII; treat accordingly

**Status:** Accepted
**Date:** 2026-05-19

## Context

Parcel data carries owner names + mailing addresses, which together meet most definitions of personally identifiable information (PII) even when individually public-record.

## Decision

- (a) No public hosting of composite outputs until access controls exist.
- (b) `data/` and `data/processed/` are git-ignored.
- (c) Sharing outputs externally requires an explicit reason logged in `docs/SECURITY.md`.

## Consequences

Real owner data stays out of the repo because `data/` is git-ignored. Demo screenshots that show real owner names may need redaction depending on audience.
