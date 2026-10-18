# ADR-063: File-based credentials, teams as tenants, and per-request file authority

**Status:** Accepted. **Shipped** in five slices. **Storage superseded on 2026-06-12** by [ADR-069](0069-credentials-in-db-cookie-sessions-gated-data-plane.md): credentials now live in the app database's `credential` table, not `users.txt`. The **authority model and invariants stand unchanged**: per-request authority, identity-only JWT, teams as tenants (registration order replaces file order), fail-closed boot, and CLI-only writes.
**Supersedes:** the credential-store and revocation portions of [ADR-062](0062-username-password-replaces-magic-link.md) (the `APP_USERS` env secret and its "no server-side revocation" trade-off). The username/password front door, the brute-force throttle, the specific-401 UX, and the fail-closed posture from ADR-062 stand unchanged.
**Date:** 2026-06-02
**Pairs with:** [ADR-055](0055-hosted-private-backend.md) (tenant-shaped backend), [ADR-062](0062-username-password-replaces-magic-link.md) (username/password front door).

## Context

ADR-062 put credentials in an `APP_USERS` env var. That worked for two users, but managing it meant hand-editing a string of hashes and redeploying. Sessions could not be revoked server-side (a removed user kept access until their 30-day JWT expired), and there was no concept of teams: every user shared one lead board.

The 2026-06-01 requirements asked for three things: sign-in as the front gate of the whole app (the map previously rendered landowner PII to anyone), **teams** that share a lead board while staying invisible to other teams, and a simple file-based way to manage users that takes effect immediately.

## Decision

Three coupled decisions, shipped together:

1. **A git-ignored plain-text file is the only credential source.** `backend/users.txt` (path overridable with `APP_USERS_FILE`) holds one `username:pbkdf2-hash:team` line per user, with `#` comments. Malformed lines are skipped, and usernames and teams are normalized (trimmed and lowercased). A committed `users.txt.example` documents the format, and a commit-guard test fails the suite if a real credentials file is ever tracked. The `APP_USERS` env var is gone. A CLI (`python -m app.users` with add, remove, list, set-password and set-team; atomic writes; never prints hashes) is the management interface.

2. **Teams are tenants.** A `tenant` table records an id and a unique normalized name. Team isolation **is** the existing ADR-055 tenant isolation, with no new machinery. Teams are find-or-created in **credentials-file order** on every login and request, so the first team in the file owns tenant 1 and inherits the pre-teams lead board (deterministic, administrator-controlled, no migration code). Each user has one team, and the `User` row syncs to the user's current team. Tenant rows are never deleted.

3. **The file is authoritative on every request.** The session JWT carries *identity only* (subject = username; no tenant claim). On each API request the backend re-checks the file to confirm the username still exists and to resolve its *current* team and tenant. The check is mtime-cached (`CredentialsFile`), so an unchanged file costs one `stat`, never a re-parse. As a result, removing a user revokes access on their **next request** (not at session expiry), changing a user's team re-homes their live session, and file edits never need a restart. The 30-day session TTL is purely a convenience.

## Consequences

- **Revocation is real.** ADR-062's "no server-side revocation" trade-off is gone: `python -m app.users remove <name>` locks a user out on their next click. Rotating `AUTH_JWT_SECRET` remains the kill-everything switch.
- **A token can never out-rank the file.** Even a token signed with the real secret but carrying forged claims gets its authorization from the file at request time (pinned by a test).
- **The cost** is a `stat` plus two indexed SELECTs per authenticated request (tenant by name, user by username). That is negligible at this scale. A per-request cache TTL is the fix if it ever matters.
- **Production hosting narrows** to mounting the credentials file (a secret-store file mount) and setting `AUTH_JWT_SECRET`. No DB-backed user admin is needed.
- **Static map data stayed unauthenticated** at this point and was recorded as a pre-hosting blocker in [LIMITATIONS.md](../LIMITATIONS.md). ADR-069 later gated the data plane.
- Multi-instance deployments re-read the same mounted file per request, so user management stays consistent across replicas. The login throttle stays per-process, unchanged from ADR-062.

## Alternatives considered

- **A DB-backed users table with an admin UI.** Rejected for the two-person phase. The file and CLI are the whole management interface, diffable and mountable from any secret store. A web UI was out of scope.
- **Login-time-only file authority** (sessions keep their login-time team and existence). Rejected by explicit decision: revocation and re-teaming must not wait out a 30-day session.
- **Plaintext passwords in the file** (convenience). Rejected by explicit decision: hashes only, and the CLI removes the inconvenience.
- **Carrying the team in the JWT** and re-validating only existence. Rejected. It creates two sources of truth for tenancy. The file alone decides.
