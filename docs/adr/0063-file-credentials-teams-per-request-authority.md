# ADR-063: File-based credentials, teams-as-tenants, and per-request file authority

**Status:** Accepted — **Shipped** via PRD #83 (#84 / PR #89, #85 / PR #90, #86 / PR #91, #87 / PR #93, #88 — this ADR). **Storage superseded 2026-06-12** by [ADR-069](0069-credentials-in-db-cookie-sessions-gated-data-plane.md) (PRD #130): credentials now live in the app database's `credential` table, not `users.txt`. The **authority model and invariants stand unchanged** — per-request authority, identity-only JWT, teams-as-tenants (registration order replaces file order), fail-closed boot, CLI-only writes.
**Supersedes:** the credential-store and revocation portions of [ADR-062](0062-username-password-replaces-magic-link.md) (the `APP_USERS` env secret and its "no server-side revocation" trade-off). The username/password front door, the brute-force throttle, the specific-401 UX, and the fail-closed posture from ADR-062 stand unchanged.
**Date:** 2026-06-02
**Pairs with:** [ADR-055](0055-hosted-private-backend.md) (tenant-shaped backend), [ADR-062](0062-username-password-replaces-magic-link.md) (username/password front door).

## Context

ADR-062 put credentials in an `APP_USERS` env var: workable for two users, but managing it meant hand-editing a string of hashes and redeploying, sessions could not be revoked server-side (a removed user kept access until their 30-day JWT expired), and there was no concept of teams — every user shared one lead board.

PRD #83 (2026-06-01) asked for three things: sign-in as the front gate of the whole app (the map previously rendered landowner PII to anyone), **teams** that share a lead board while being invisible to other teams, and a simple file-based way to manage users that takes effect immediately.

## Decision

Three coupled decisions, shipped as one PRD:

1. **A git-ignored plain-text file is the only credential source.** `backend/users.txt` (path overridable via `APP_USERS_FILE`): one `username:pbkdf2-hash:team` line per user, `#` comments, malformed lines skipped, usernames/teams normalized (trimmed + lowercased). A committed `users.txt.example` documents the format; a commit-guard test fails the suite if a real credentials file is ever tracked. The `APP_USERS` env var is gone. A CLI (`python -m app.users` — add / remove / list / set-password / set-team, atomic writes, never prints hashes) is the management surface (#87).

2. **Teams are tenants.** A `tenant` table records id + unique normalized name; team isolation **is** the existing ADR-055 tenant isolation — no new machinery. Teams are find-or-created in **credentials-file order** on every login/request, so the first team in the file owns tenant 1 and thereby inherits the pre-teams lead board (deterministic, administrator-controlled, no migration code). One team per user; the `User` row syncs to the user's current team. Tenant rows are never deleted.

3. **The file is authoritative on every request.** The session JWT carries *identity only* (subject = username; no tenant claim). On each API request the backend re-checks the file — mtime-cached (`CredentialsFile`), so an unchanged file costs one `stat`, never a re-parse — to confirm the username still exists and to resolve its *current* team → tenant. Consequences: removing a user revokes their access on their **next request** (not at session expiry); changing a user's team re-homes their live session; file edits never require a restart. The 30-day session TTL remains purely a convenience.

## Consequences

- **Revocation is real.** ADR-062's "no server-side revocation" trade-off is gone: `python -m app.users remove <name>` locks a user out on their next click. Rotating `AUTH_JWT_SECRET` remains the kill-everything switch.
- **A token can never out-rank the file.** Even a token signed with the real secret but carrying forged claims gets its authorization from the file at request time (pinned by test).
- **The cost** is a `stat` + two indexed SELECTs per authenticated request (tenant by name, user by username) — negligible at this product's scale; revisit with a per-request cache TTL if it ever matters.
- **#16 (production hosting) narrows** to: mount the credentials file (a secret-store file mount) + set `AUTH_JWT_SECRET`. No DB-backed user admin needed.
- **Static map data remains unauthenticated** — documented as a pre-hosting blocker in [LIMITATIONS.md](../LIMITATIONS.md); the fix is reverse-proxy auth at hosting time, not application code.
- Multi-instance deployments re-read the same mounted file per request, so user management stays consistent across replicas (the login throttle remains per-process — unchanged from ADR-062).

## Alternatives considered

- **DB-backed users table + admin UI.** Rejected for the two-person phase — the file + CLI is the entire management surface, diffable and mountable from any secret store; a web UI is listed out-of-scope in PRD #83.
- **Login-time-only file authority** (sessions keep their login-time team/existence). Rejected by explicit user decision in the PRD grilling — revocation and re-teaming must not wait out a 30-day session.
- **Plaintext passwords in the file** (convenience). Rejected by explicit user decision — hashes only; the CLI removes the inconvenience.
- **Carrying the team in the JWT** and re-validating only existence. Rejected — two sources of truth for tenancy; the file alone decides.
