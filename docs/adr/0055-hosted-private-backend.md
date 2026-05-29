# ADR-055: Hosted-private backend with tenant-shaped schema from Day 1

**Status:** Accepted — **locked design, UNIMPLEMENTED as of 2026-05-29 (Slice 4; no `backend/` code exists yet).**
**Supersedes:** ADR-006 (static-site, no backend) — for write-layer features only; read-only analytical layers stay static.
**Date:** 2026-05-25
**Pairs with:** ADR-053

## Context

ADR-006 (2026-05) committed to a static-site model — no backend, all filtering / search in DuckDB-WASM, parquet over HTTP. Correct for the pitch cut (read-only analytical demo).

The product phase (ADR-053) introduces requirements the static model cannot satisfy:

- Lease document upload + LLM extraction (Slice 4 D)
- Persistent lead state across sessions (Slice 4 E)
- Per-user activity log
- Auth
- Optional Phase 2 mass-email + response tracking

The user (2026-05-25): *"the goal here is to get as much data as possible so in the future we will have to look into how to start paying for and accessing more data"* — strongly implies eventual paid data + potential multi-tenant sale of the tool to other land-side consultants.

## Decision

Slice 4 stands up a **hosted-private backend** alongside the existing static map app:

- Small VM (Fly.io / Render / Hetzner class) — $30–100/mo Phase 1
- **Postgres** (testcontainers in CI; managed Postgres in prod)
- **S3-compatible object store** for lease PDFs (Backblaze B2 / Cloudflare R2 / AWS S3) — encrypted at rest, signed download URLs
- **Thin FastAPI** app for the lead / lease / activity CRUD
- **Claude API** for lease document extraction (see ADR-059)
- **Magic-link auth** over email — lowest friction for 2-5 users

**Tenant-shaped schema from Day 1:** every table has a `tenant_id` column, always reads `1` for now. Multi-tenancy isolation tests written from Day 1 even with only 1 tenant. Adding a second tenant (intern / advisor / second cofounder / paid Phase-3 customer) is a row add, not a refactor.

The map app stays a static site; it now talks to the backend over a thin API for lead/lease state while continuing to read parquet + PMTiles via HTTP range requests for the static analytical layers.

## Consequences

- ADR-006 retired for write-layer features; read-only analytical layers stay static.
- PII custody implications grow — backend handles owner names + uploaded lease PDFs (containing owner identity + rent terms). HTTPS, encrypted at rest, signed downloads required (per ADR-040).
- ~$30–100/mo Phase 1 hosting cost — within ADR-010 reframed posture (see ADR-057).
- Multi-tenant Phase-3 path feasible without rewrite.
- Test surface grows substantially — see [TESTING.md §11](../TESTING.md) for the Slice 4 additions.

## Alternatives considered

- **Local-only ($0):** rejected; ops friction between co-founder's and dev's laptops is real; cost saving is small.
- **Hosted multi-tenant from Day 1:** rejected as over-engineering — no second tenant yet, would guess what they need. Tenant-shaped schema gives the option without the cost.
