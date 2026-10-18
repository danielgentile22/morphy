# ADR-055: Hosted-private backend with tenant-shaped schema from day 1

**Status:** Accepted. **Implemented**: the write layer and auth landed through the lead-centric triage redesign ([ADR-061](0061-lead-centric-triage-redesign.md)). Lease upload, LLM extraction and object storage for lease PDFs were never built. The **magic-link auth portion is superseded by [ADR-062](0062-username-password-replaces-magic-link.md)** (username/password login). The rest (hosted-private backend, tenant-shaped schema, JWT sessions) stands. [ADR-064](0064-phase1-hosting-fly-sqlite.md) later narrowed the platform, database and object store.
**Supersedes:** ADR-006 (static site, no backend), for write-layer features only. Read-only analytical layers stay static.
**Date:** 2026-05-25
**Pairs with:** ADR-053

## Context

ADR-006 (2026-05) committed to a static-site model: no backend, all filtering and search in DuckDB-WASM, parquet over HTTP. That was right for a read-only analytical demo.

The product phase (ADR-053) brings requirements the static model cannot meet:

- Lease document upload and LLM extraction (Slice D)
- Persistent lead state across sessions (Slice E)
- A per-user activity log
- Auth
- Optional Phase 2 mass email with response tracking

The data strategy also expected paid data sources later, and possibly more than one team using the tool.

## Decision

Slice D+E stands up a **hosted-private backend** alongside the existing static map app:

- A small VM (Fly.io, Render or Hetzner class), budgeted at $30-100/mo for Phase 1
- **Postgres** (testcontainers in CI, managed Postgres in production)
- An **S3-compatible object store** for lease PDFs (Backblaze B2, Cloudflare R2 or AWS S3), encrypted at rest, with signed download URLs
- A **thin FastAPI** app for lead, lease and activity CRUD
- The **Claude API** for lease document extraction (see ADR-059)
- **Magic-link auth** over email, the lowest-friction option for 2-5 users

**Tenant-shaped schema from day 1:** every table has a `tenant_id` column, which always reads `1` for now. Multi-tenancy isolation tests exist from day 1 even with one tenant. Adding a second tenant (another team or collaborator) is a row insert, not a refactor.

The map app stays a static site. It talks to the backend over a thin API for lead and lease state, and keeps reading parquet and PMTiles over HTTP range requests for the static analytical layers.

## Consequences

- ADR-006 retires for write-layer features. Read-only analytical layers stay static.
- PII custody grows. The backend handles owner names and uploaded lease PDFs, which contain owner identity and rent terms. HTTPS, encryption at rest and signed downloads are required (per ADR-040).
- Phase 1 hosting costs about $30-100/mo, within the reframed budget posture of ADR-057.
- A multi-tenant path stays open without a rewrite.
- The test suite grows substantially. See [TESTING.md](../TESTING.md) for the backend additions.

## Alternatives considered

- **Local-only ($0).** Rejected. Keeping data in sync between the analyst's and the developer's laptops is real friction, and the saving is small.
- **Hosted multi-tenant from day 1.** Rejected as over-engineering. With no second tenant, the design would guess at its needs. A tenant-shaped schema keeps the option open at no cost.
