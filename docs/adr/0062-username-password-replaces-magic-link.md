# ADR-062: Username/password login replaces magic-link; magic-link machinery removed

**Status:** Accepted. **Shipped** in three slices: the credential path, its hardening, and this removal.
**Supersedes:** the magic-link auth portion of [ADR-055](0055-hosted-private-backend.md) and its implementation (the request-link → exchange flow). The rest of ADR-055 (hosted-private backend, `tenant_id` from day 1, the JWT and tenant-resolution seam) stands unchanged.
**Date:** 2026-05-31
**Pairs with:** [ADR-055](0055-hosted-private-backend.md) (backend), [ADR-061](0061-lead-centric-triage-redesign.md) (the redesign whose write layer this auth gates).

## Context

ADR-055 specified **magic-link** sign-in: email a one-time, hashed, expiring token, then redeem it for a session JWT. The first backend build implemented it with `email_sender.py`, the `magic_link_token` table and token crypto, and the `POST /api/auth/request-link` and `POST /api/auth/exchange` routes, behind a fail-closed `AUTH_DEV_MODE` posture.

Magic-link assumes a working email transport: a real `EmailSender` (SES, Postmark or SMTP) plus an allowlist or invite flow. None of that existed. For a **two-person** project with a single daily user, that delivery dependency is pure friction. There is no inbox to receive the link in the dev loop, and standing up a transport so two known people can sign in is out of proportion.

On 2026-05-31 the front door was replaced with **hardcoded username/password logins**: a small `{username -> hash}` credential set provisioned from an `APP_USERS` env secret, checked at `POST /api/auth/login`, minting the same HS256 session JWT. The first slice landed the credential path. The second hardened it with a brute-force login throttle and a fail-closed boot guard keyed on the credential set instead of the magic-link allowlist. After the first slice the magic-link routes were **dormant**: unused by the SPA, their tests already removed, but still present as dead code.

## Decision

Remove the magic-link machinery entirely. Username/password (`POST /api/auth/login` → HS256 JWT) is the **only** front door.

Deleted: `email_sender.py` (the `EmailSender` protocol and the console and recording senders); the `MagicLinkToken` model and `magic_link_token` table (no destructive migration: the orphaned dev-SQLite table is harmless, and Postgres simply stops creating it); the one-time-token crypto (`generate_token` / `hash_token`) in `auth.py`; the `request_link` / `exchange` / token-pruning code in `auth_service.py` (slimmed to the `login` and `provision_user` keepers); the `RequestLinkBody` / `RequestLinkResponse` / `ExchangeBody` schemas; the two routes and their sender wiring; and the dead config knobs (`allowed_emails`, `allow_open_signup`, `expose_token_in_response`, `link_ttl_minutes`, `link_rate_*` and their `AUTH_*` env reads).

**Untouched:** the JWT seam (`Principal`, `create_access_token`, `decode_access_token`, `current_principal`, `current_tenant_id`, the `HTTPBearer` dependency), the `User` model, tenant isolation, and the login throttle and fail-closed boot guard. After the removal the app logs in and serves tenant-scoped data exactly as before.

## Consequences

- One auth path to reason about, and no dormant, untested routes inviting drift.
- `email_sender.py` and a real email transport are no longer prerequisites. Production hosting narrows to "put the `APP_USERS` secret and the JWT secret in a real secret store."
- Adding a user is a row in `APP_USERS` (a hash from `python -m app.password`), not an invite or email flow.
- Docs that described magic-link (`backend/README.md`, `CLAUDE.md`, `docs/STATUS.md`) were updated to the username/password scheme.
- The removal is recoverable from git history and this ADR if email-based onboarding is ever wanted again. It would come back as a new decision, not by reviving this code.

## Alternatives considered

- **Keep magic-link dormant.** Rejected. Dead, untested code on the auth path is a liability.
- **Drop the routes but keep `email_sender.py` and the token table for a future revival.** Rejected as speculative. The clean deletion is recoverable from git.
- **Build the real `EmailSender` and keep magic-link.** Rejected for the two-person phase. It is out of proportion for onboarding two known users. Worth revisiting only if many more users or teams arrive (the multi-tenant path ADR-055 anticipates).
