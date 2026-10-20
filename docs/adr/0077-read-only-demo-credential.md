# ADR-077: A read-only demo credential behind DEMO_MODE; Ask Claude retired

**Status:** Accepted. Implemented in the public demo deployment (`morphy-demo`). Decision 5 amended by [ADR-078](0078-demo-leads-over-government-owners.md) (seed government owners only).
**Date:** 2026-10-18
**Amends:** [ADR-069](0069-credentials-in-db-cookie-sessions-gated-data-plane.md) (adds a column to the `credential` table and a second way to start a session; its authority invariants stand unchanged).
**Pairs with:** [ADR-062](0062-username-password-replaces-magic-link.md), [ADR-063](0063-file-credentials-teams-per-request-authority.md), [ADR-068](0068-self-service-password-change.md).

## Context

The app is going public as a portfolio demo at `https://morphy-demo.fly.dev`. Anyone should be able to open it and look around without being handed a password, and nobody should be able to change anything. The existing auth posture is load-bearing: credentials live only in the `credential` table and re-authorize every request (API routes and the edge-gated `/data/processed/*` alike), the JWT carries identity only, and boot fails closed.

Separately, the "Ask Claude" route (`POST /api/audit/ask`, the `ask_log` table, the Anthropic client) had one client, the data-audit site, which has been deleted. The route was dead code with a paid-API dependency.

## Decision

1. **Read-only is a property of a credential.** The `credential` table gains `read_only` (boolean, not null, default false, so every existing credential keeps full access). `python -m app.users add <user> <team> --read-only` creates one; `set-read-only <user> on|off` flips one. Like the team, the flag is read from the table on every request, so a change applies on the next click.

2. **One gate.** `current_principal`, the dependency every authenticated route already resolves its caller through, refuses a read-only principal's non-GET/HEAD/OPTIONS request with 403 and a plain message. No per-route checks, and a future write route is covered without anyone remembering to add a check. Sign-in, sign-out, and the demo login never resolve a principal, so they stay open. The self-service password change (`POST /api/me/password`) is refused like any other write.

3. **`DEMO_MODE` adds a password-less sign-in for exactly one credential.** Off unless the env var is explicitly truthy (same parsing as `AUTH_DEV_MODE`). When on:
   - `POST /api/auth/demo` issues the normal identity-only JWT in the normal httpOnly session cookie for the credential named by `DEMO_USERNAME` (default `demo`). It re-checks on every call that the credential exists and is read-only, and answers 404 otherwise, so it can never hand out a writable session. When `DEMO_MODE` is off it is a 404.
   - Boot refuses to serve unless that credential exists and is read-only (`ensure_fail_closed_boot`). The switch cannot be turned on by accident against a writable account.
   - `GET /api/auth/config` (public) tells the sign-in page whether to show "Explore the demo".
   - The Origin/Referer check still covers the demo route (it is a POST), which stops a cross-site page from silently signing a visitor in. There is no password, so the login throttle does not apply to it.

4. **The edge gate is unchanged.** The demo user is a real credential row, so Caddy's `forward_auth` to `/api/auth/check` passes it exactly as it passes any signed-in user, and removing the row ends the demo's data access on the next fetch.

5. **Seeding.** `python -m app.demo_seed` (idempotent) creates the demo team and read-only credential with a random password printed once and stored nowhere else, then puts six fictional storylines on the demo board over top-scoring business-entity owners from the owners index (never individuals). Notes say they are fictional; contact fields stay blank. A board that already has leads is left alone; a missing owners index skips the leads but still creates the credential.

6. **The frontend reflects it, the backend enforces it.** `/api/auth/me` returns `read_only`; the SPA shows a "Read-only demo" badge and hides or disables write controls. Appearance preferences apply for the visit without a server write. Any 403 that still gets through shows one calm notice.

7. **Ask Claude is removed.** The route, `ask_assembler.py`, `ask_client.py`, `ask_log_store.py`, their tests, the `ANTHROPIC_API_KEY`/`ASK_*` settings, and the backend's `anthropic` dependency are deleted. Alembic revision `0003` drops `ask_log` in the same revision that adds `read_only`. The puller's `anthropic` dependency stays: the data TUI's diagnose action (`scripts/diagnose.py`) still uses it, locally only.

## What explicitly does NOT change

- **Per-request authority.** The demo session is re-authorized against the table on every API request and every data fetch.
- **Identity-only JWT.** No read-only claim, no tenant claim. The flag lives only in the table.
- **Fail-closed boot.** `DEMO_MODE` adds a condition; it relaxes none.
- **Sanctioned credential writers.** Still the CLI and the caller's own password change. The demo seed is a CLI run by an operator on the machine, writing through the same store functions.

## Consequences

- The first deploy with `DEMO_MODE=1` needs one operator step before the backend will boot: run the seed on the machine.
- A visitor sees real public-record data (the owners index, parcels, towers) and fictional lead state. The demo tenant is isolated from any other team's board by the existing tenant rule.
- Every write path is regression-tested by a test that enumerates the app's non-GET routes and asserts 403 for a read-only principal, so a new route cannot slip past the gate unnoticed.
- One fewer paid-API dependency and one fewer table in the backend.

## Alternatives considered

- **A middleware that decodes the token and checks the flag.** Rejected: it would duplicate the authority lookup `current_principal` already does, and need its own exemption list.
- **A read-only claim in the JWT.** Rejected: it breaks the identity-only invariant and would outlive a flag change until expiry.
- **Publishing a shared demo password.** Rejected: a password on a public page invites reuse and credential-stuffing noise against the throttle, for no benefit over a button.
- **Keeping Ask Claude dormant.** Rejected: no client, a paid dependency, and an unused table.
