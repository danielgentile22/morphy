# ADR-069: Credentials move to the app database; cookie sessions; the data plane is gated at the edge

**Status:** Accepted. **Shipped** in five stages, completed 2026-06-12.
**Amends:** [ADR-063](0063-file-credentials-teams-per-request-authority.md). Its **storage mechanism** (`users.txt`) is superseded; its **authority model and invariants stand unchanged**. This ADR also re-homes the [ADR-068](0068-self-service-password-change.md) sanctioned-writer rule onto the DB store, and closes the "static map data remains unauthenticated" pre-hosting blocker ADR-063 documented.
**Date:** 2026-06-12
**Pairs with:** [ADR-062](0062-username-password-replaces-magic-link.md) (username/password front door, untouched), [ADR-064](0064-phase1-hosting-fly-sqlite.md) (Fly + SQLite + Litestream hosting).

## Context

An architecture decision review on 2026-06-11 verified three coupled exposures in the hosted app:

1. **The whole served composite was downloadable unauthenticated.** The sign-in gate protected the app shell and `/api/*`, but `/data/processed/*` (owners index, parquet, PMTiles, GeoJSON; parcel-owner PII) answered any request that knew a URL. A range request to the hosted owners index returned `206` with content.
2. **The session JWT sat in `localStorage`**, readable by any XSS.
3. **`users.txt` was the one piece of irreplaceable state Litestream did not replicate.** Lose the volume, lose every login.

## Decision

One coherent change, shipped in order: interim file backup → cookie transport → edge gate → credentials-in-DB → file retirement.

1. **Same token, new transport.** The identity-only HS256 JWT is unchanged. Login sets it in an **httpOnly / Secure / SameSite=Lax cookie** (`morphy_session`). The body token remains for non-browser clients, and `Authorization: Bearer` stays accepted (the cookie is checked first). A sign-out endpoint clears the cookie. CSRF posture: SameSite=Lax plus an Origin/Referer-check middleware on non-GET `/api` routes, with no token-dance machinery for a same-origin internal tool.

2. **The edge asks before serving data.** Caddy's `forward_auth` gates `/data/processed/*` behind a new lightweight `GET /api/auth/check` (cookie or bearer → username still credentialed? → 204/401, no body, no tenant resolution). Because the cookie rides automatically on MapLibre tile fetches, PMTiles range requests, and DuckDB-WASM parquet reads, no frontend data library needed changes. The health endpoint stays public, the volume-root 404 wall stays, and `Cache-Control: private, no-store` stays.

3. **Credentials live in the `credential` table**, the only credential source. One row replaces one file line (normalized unique username, the same self-describing PBKDF2 hash, normalized team). **Registration order (`id`) replaces file order** for teams-as-tenants: the first credential's team owns tenant 1. `python -m app.users` keeps its exact subcommands against the DB and gains `import-file` (one-shot; refuses a non-empty table). The cutover deploy self-migrated. An empty table at boot imported `/data/users.txt` in file order, preserving every team→tenant assignment.

4. **Fail-closed boot is enforced at startup** (`ensure_fail_closed_boot`), no longer at config import. Outside dev mode the app refuses to *serve* without a real `AUTH_JWT_SECRET` and **≥ 1 credential row**. Dev mode seeds `dev`/`dev` through the same store writer the CLI uses, so dev cannot bypass the production code path.

5. **Retirement.** `users.txt` is no longer consulted anywhere. The `APP_USERS_FILE` knob, the boot import, the mtime-cached `CredentialsFile` reader, and the interim off-site backup loop are gone. The file format survives only as the `import-file` input. The commit-guard test keeps `users.txt` untracked (legacy hygiene) and also guards the SQLite DB, which holds the hashes.

## What explicitly does NOT change (the ADR-062/063 invariants)

- **Per-request authority.** The credential table is consulted on every API request *and every data fetch*, so removal or re-teaming applies on the next click. A token can never out-rank the store.
- **Identity-only JWT.** No tenant claims, ever. Existing sessions survived the storage cutover because the token carries nothing the storage change touched.
- **Teams are tenants.** Same find-or-create, same first-registered-owns-tenant-1 inheritance. The import preserved existing tenant rows.
- **Fail-closed posture**, the brute-force login throttle, and the specific-401 login UX.
- **The CLI and self-service password change remain the only sanctioned credential writers** (ADR-068's rule, re-pointed at the store).

## Consequences

- **The PII exposure class is regression-gated twice.** The Caddy fixture test (real binary) proves unauthenticated `/data/processed/*` → 401 with zero file bytes while authenticated range requests still get 206. `deploy.sh smoke` asserts the unauthenticated probe returns 401/403 after every deploy.
- **Credentials are covered by continuous replication.** They ride the same Litestream stream as lead state. The interim `backup_users.sh` loop (stage 1) was retired with the file.
- **Page scripts can no longer read the session token.** Sign-out revokes the browser's data access, because the next `forward_auth` check fails.
- Every `/data/processed/*` fetch costs one backend round-trip (an indexed SELECT). That is negligible against the file reads it gates, and burst-friendly (no tenant or user resolution on the check path).
- The per-request cost of authorization is three indexed SELECTs (credential, tenant, user). The file-era stat+parse cache retired with the file, along with the per-request principal memo whose invalidation signal *was* the file mtime.
- **Ops change.** User management still runs `python -m app.users …` on the machine, now writing the DB. `DATABASE_URL` (already in `fly.toml`) is the only knob. Hand-editing hashes is no longer even possible.

## Alternatives considered

- **Signed URLs or CDN-level access control** for the data plane. Rejected in the review: per-URL signing breaks range-request semantics and adds key-distribution machinery, while `forward_auth` reuses the session that already exists.
- **CSRF tokens.** Rejected. SameSite=Lax plus the Origin check suffices for a same-origin two-person tool.
- **Keeping the file and adding it to Litestream-style replication.** Rejected. It leaves two storage systems where one (the already-replicated DB) suffices, and the file's mtime-cache machinery existed only to make per-request file authority affordable.
