# ADR-062: Username/password login replaces magic-link; magic-link machinery removed

**Status:** Accepted — **Shipped** via PRD #75 (Slice 1 #76 / PR #79, Slice 2 #77 / PR #81, Slice 3 #78 — this ADR).
**Supersedes:** the magic-link auth portion of [ADR-055](0055-hosted-private-backend.md) and its implementation in **PR #48** (the request-link → exchange flow). The rest of ADR-055 (hosted-private backend, `tenant_id` Day 1, the JWT / tenant-resolution seam) stands unchanged.
**Date:** 2026-05-31
**Pairs with:** [ADR-055](0055-hosted-private-backend.md) (backend), [ADR-061](0061-lead-centric-triage-redesign.md) (the redesign whose write-layer this auth gates).

## Context

ADR-055 specified **magic-link** sign-in — email a one-time, hashed, expiring token; redeem it for a session JWT — and #48 (PR #56) implemented it: `email_sender.py`, the `magic_link_token` table + token crypto, and the `POST /api/auth/request-link` + `POST /api/auth/exchange` routes, behind a fail-closed `AUTH_DEV_MODE` posture.

Magic-link assumes a working email transport — a real `EmailSender` (SES / Postmark / SMTP) plus an allowlist / invite flow (#16) — none of which exists yet. For a **two-person** product whose co-founder is the sole daily user, that delivery dependency is pure friction: there is no inbox to receive the link in the dev loop, and standing up a transport just to let two known people sign in is disproportionate.

PRD #75 (2026-05-31) replaced the front door with **hardcoded username/password logins**: a small `{username -> hash}` credential set provisioned from an `APP_USERS` env secret, checked at `POST /api/auth/login`, minting the same HS256 session JWT. Slice 1 (#76) landed the credential path; Slice 2 (#77) hardened it (a brute-force login throttle + a fail-closed boot guard re-keyed on the credential set rather than the magic-link allowlist). After #76 the magic-link routes were **dormant** — unused by the SPA, their tests already removed — but still present as dead code.

## Decision

Remove the magic-link machinery entirely (Slice 3 / #78). Username/password (`POST /api/auth/login` → HS256 JWT) is the **only** front door.

Deleted: `email_sender.py` (the `EmailSender` protocol + console / recording senders); the `MagicLinkToken` model + `magic_link_token` table (no destructive migration — the orphaned dev-SQLite table is harmless, and Postgres simply stops creating it); the one-time-token crypto (`generate_token` / `hash_token`) in `auth.py`; the `request_link` / `exchange` / token-pruning code in `auth_service.py` (slimmed to the `login` + `provision_user` keepers); the `RequestLinkBody` / `RequestLinkResponse` / `ExchangeBody` schemas; the two routes and their sender wiring; and the now-dead config knobs (`allowed_emails`, `allow_open_signup`, `expose_token_in_response`, `link_ttl_minutes`, `link_rate_*` and their `AUTH_*` env reads).

**Untouched:** the JWT seam (`Principal`, `create_access_token`, `decode_access_token`, `current_principal`, `current_tenant_id`, the `HTTPBearer` dependency), the `User` model, tenant isolation, and the #77 throttle + fail-closed boot guard. After removal the app logs in and serves tenant-scoped data exactly as before.

## Consequences

- One auth path to reason about; no dormant, untested routes inviting drift.
- `email_sender.py` and a real email transport are no longer prerequisites; #16 narrows to "host the `APP_USERS` secret + the JWT secret in a real secret store."
- Adding a user is a row in `APP_USERS` (a hash from `python -m app.password`), not an invite / email flow.
- Docs that described magic-link (`backend/README.md`, `CLAUDE.md`, `docs/STATUS.md`) are updated to the username/password scheme.
- The removal is recoverable from git + PR #48 + this ADR if email-based onboarding is ever wanted again — but it would return as a new decision, not by reviving this code.

## Alternatives considered

- **Keep magic-link dormant.** Rejected — dead, untested code on the auth surface is a liability, and the PRD #75 direction is committed.
- **Drop the routes but keep `email_sender.py` + the token table for a future revival.** Rejected — speculative; the clean deletion is recoverable from git.
- **Build the real `EmailSender` (#16) and keep magic-link.** Rejected for the two-person phase — disproportionate to onboard two known users; revisit if the tool is sold to other consultants (the multi-tenant path ADR-055 anticipates).
