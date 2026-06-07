# ADR-068: Self-service password change is a sanctioned runtime caller of the credentials writer

**Status:** Accepted — **Shipped** via PRD #121 (Settings page).
**Date:** 2026-06-07
**Pairs with:** [ADR-063](0063-file-credentials-teams-per-request-authority.md) (file-based credentials, per-request file authority), [ADR-064](0064-phase1-hosting-fly-sqlite.md) (Fly + SQLite + Litestream hosting).

## Context

ADR-063 made `backend/users.txt` the only credential source and established the rule that the file is managed **only** via the `app.users` API (`python -m app.users …`) — never by hand-editing hashes. A teammate who wanted to change their own password therefore needed an administrator at a shell.

PRD #121 (the per-user Settings page) adds self-service: a signed-in user changes their own password from **Settings → Account**. This is the first time the *running web app* (not the CLI) writes to the credentials file — a deliberate, narrow departure from "credentials are CLI-managed only" that needs to stay safe.

## Decision

The password endpoint **reuses the one sanctioned writer**; it does not introduce a second file-writing path.

1. A small, unit-testable policy function `users.change_password(file, username, current, new) -> ChangePasswordOutcome` composes two existing primitives:
   - `password.verify_password` — constant-time check of the *current* password against the stored hash;
   - `users.set_password` — the existing atomic temp-file-+-rename writer that preserves the line's **team** and **file position** and bumps mtime.

   The current password is verified **first**, so a wrong guess returns `WRONG_CURRENT` and the file is left **byte-for-byte unchanged**. An empty new password (or an unknown user) raises `UsersFileError`. Other users' lines are byte-preserved.

2. `POST /api/me/password` (behind the existing `current_principal` dependency, scoped to the signed-in username) is a thin wrapper: `WRONG_CURRENT` → 401 (the same specific-rejection UX as login), `UsersFileError` → 422, success → 204. The credentials-file path is the existing `settings.credentials_path` (`APP_USERS_FILE`, the volume-backed `/data/users.txt` in prod).

   Because the file is authoritative on every request (ADR-063) and `set_password` bumps mtime, the new credential is **live on the user's next request** — no redeploy, no restart.

The invariant is **amended, not broken**: "manage `users.txt` only via the `app.users` API" still holds — the endpoint *calls that API* (`change_password` → `set_password`); it never hand-edits a hash.

## Consequences

- **No new attack surface on the file format.** The endpoint can only rotate the *caller's own* hash (the username comes from the verified principal, not the request body) and only through the audited atomic writer; it cannot change teams, add/remove users, or touch another line.
- **Out of scope stays out of scope.** Forgot-password / lockout recovery remains an administrator action (`python -m app.users set-password`); there is no email/reset flow.
- **Prod caveat (write target).** In production, `users.txt` lives on the Fly volume and is **not** Litestream-replicated like the SQLite DB ([ADR-064](0064-phase1-hosting-fly-sqlite.md)). A self-service password change persists on the volume; treat the volume as the source of truth for credentials and snapshot it accordingly. Recreating the machine without the volume reverts credentials to whatever the mounted file last held.
- **Documented** in `backend/README.md` and `backend/AGENTS.md` as the *one* sanctioned runtime caller of `users.set_password`.
