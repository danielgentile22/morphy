# Security and data handling

**Archived.** The project is no longer under development. This file records the data-handling
posture as it stood when work stopped.

This document records how the project handles data that contains personally identifying
information (PII), what it treats as sensitive, and the guardrails around it. It backs
[ADR-040](./adr/0040-parcel-owner-pii.md) and [ADR-041](./adr/0041-no-llc-unmasking.md) (narrowed
by [ADR-057](./adr/0057-budget-posture-reframed.md)), indexed in [DECISIONS.md](./DECISIONS.md).

It is **not** a full infosec policy. It is the project-specific posture for a very small team on
free-tier hosting.

The repository is public. No raw data, composite outputs, database files, credentials, or secrets
are committed to it: `data/` is git-ignored, the app database lives only on the host volume, and
secrets come from git-ignored `.env` files locally and the host's secret store in deployment.

---

## 1. What counts as sensitive

| Category | Examples | Why sensitive |
|---|---|---|
| **Parcel-owner PII** | Owner name plus mailing address per parcel | Each field is public record on its own. The combination (a name tied to a specific property, valuation, and GPS location) meets most PII definitions. |
| **Composite outputs** | `data/processed/composite/<fips>/parcels.*` | Parcel-owner PII at scale. Aggregation raises the sensitivity. |
| **Lead state and activity log** | `lead.*`, `contact_attempt.*`, `task.*` | Shows which landowners a user is working and where each negotiation stands. |
| **Uploaded lease documents** (planned, never built) | PDFs in an S3-compatible object store | Owner identity, rent terms, and carrier identity in landowner-signed contracts. |
| **LLM-extracted lease fields** (planned, never built) | `lease.extracted_fields_json` plus denormalized rent, escalation, and expiry | Same sensitivity as the source PDF. |
| **Cached SoS officer lookups** (planned, never built) | Secretary of State (SoS) LLC-officer lookups in the lead-detail panel | Public records, but cached and aggregated alongside lead state. |
| **Screenshots** | Any capture of the map or lead views | May show real owner names, depending on what is on screen. |
| **Anthropic API key** | `ANTHROPIC_API_KEY`, read only by the local `scripts/diagnose.py` tool | Standard secret hygiene. |
| **Hosting and storage credentials** | Fly.io, Cloudflare R2, and Cloudflare credentials | Standard secret hygiene. |
| **Login credentials and session JWTs** | `credential`-table password hashes in the app DB (never committed; a commit-guard test enforces it) and HS256 session tokens in the httpOnly `morphy_session` cookie ([ADR-062](./adr/0062-username-password-replaces-magic-link.md), [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md), [ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)) | Leakage means account takeover. |
| **Tenant boundary** | `tenant_id` column on every backend table; every route filters by it | Teams are tenants, resolved per request (no `tenant_id=1` stub). The boundary must hold so no tenant sees another's leads. |
| **Offline output bundles** | ZIP bundles described in [DEPLOYMENT.md](./DEPLOYMENT.md) | Copies PII outside the controlled environment. |

Public-record information that is **not** sensitive on its own: parcel APN (assessor's parcel
number), geometry, assessed value, FCC Antenna Structure Registration (ASR) records, EIA plant
data, and distress-overlay polygons.

---

## 2. What the project never does

1. **Never commit raw or composite data to git.** `data/` and `data/processed/` are git-ignored.
2. **Never commit the app database or hand-edit password hashes.** Credentials are managed only
   through `python -m app.users`.
3. **Never host composite outputs or the backend without auth.** The backend is hosted-private
   ([ADR-055](./adr/0055-hosted-private-backend.md)), and the data plane (`/data/processed/*`) is
   gated at the edge by the same auth check as the API
   ([ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)). The public demo
   keeps that gate: its visitors hold a real, read-only session (section 3.3).
4. **Never share unencrypted ZIPs of composite data.** Encrypt the bundle and send the password
   through a different channel than the file.
5. **Never attempt paid LLC unmasking, shell-piercing, or identity resolution.** Permanent non-goal
   per ADR-041 as narrowed by ADR-057. The narrowing allowed free public-records officer disclosure
   (SoS business-entity lookups and UCC-1 filings), which shows only the officers an entity itself
   discloses. That is not identity resolution.
6. **Never store secrets in source code.** Locally they live in git-ignored `.env` files (the
   committed `.env.example` files list the names only). In deployment they live in Fly secrets.
7. **Never serve lease PDFs from a public URL.** The design called for S3-compatible storage with
   signed download URLs only, scoped to the requesting user's tenant. Lease storage was never
   built.
8. **Never leak cross-tenant data.** Every backend route filters by `tenant_id`, and the
   multi-tenancy isolation tests run in CI (see [TESTING.md](./TESTING.md)).
9. **Never log full owner records, lease terms, or extracted fields** in app logs. Aggregate counts
   only.

---

## 3. Controls in place

### 3.1 Data layer

| Control | Status | Where |
|---|---|---|
| `data/` git-ignored | Enforced | `.gitignore` |
| No data, database, or secrets in the public repo | Enforced | `.gitignore`; commit-guard test for the credential DB |
| Composite outputs encrypted at rest on disk | Not built | Full-disk encryption (macOS FileVault) is the only protection |
| Screenshots checked for PII before sharing | Manual | Prefer LLC-heavy AR for captures |
| API keys in env, not source | Enforced | Git-ignored `.env` |
| Composite data plane gated behind auth | Enforced in the hosted app | `/data/processed/*` gated by Caddy `forward_auth` ([ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)) |
| No LLC unmasking pipeline | Enforced | ADR-041, ADR-057 |

### 3.2 Backend layer

The backend ran on Fly.io ([ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md)) with auth,
multi-tenancy, and the activity log shipped. Lease-PDF storage and LLM lease extraction
([ADR-059](./adr/0059-llm-lease-extraction.md)) were never built; those rows describe the design.

| Control | Posture |
|---|---|
| Auth | Username and password checked against the `credential` table in the app DB (PBKDF2-HMAC-SHA256 hashes, managed with `python -m app.users`). Sessions are identity-only HS256 JWTs in the httpOnly `morphy_session` cookie. **The credential table re-authorizes every request**, so removing or re-teaming a user applies on their next click. The edge gates `/data/processed/*` through the same check ([ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md) as amended by [ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)). `AUTH_DEV_MODE` fails closed. |
| Login throttling | In-process throttle on the login route. No hard lockout, so a third party who knows a username cannot lock the real user out. |
| Multi-tenancy | `tenant_id` column on every table except `credential` and `tenant`; every route filters by it. Teams are tenants, resolved per request (no `tenant_id=1` stub). Isolation tests gate CI. |
| Lease-PDF storage *(never built)* | Designed as a private S3-compatible bucket, encrypted at rest (SSE-S3 or KMS), with signed download URLs only. |
| Database | SQLite on a Fly volume, replicated to Cloudflare R2 by Litestream ([ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md)). The ORM is DB-agnostic (Postgres-ready). Schema changes ship as Alembic revisions. |
| API transport | HTTPS only, with HSTS. HTTP redirects to HTTPS (Cloudflare proxy, Full (strict) TLS mode). |
| LLM calls | None in the shipped backend. Lease extraction *(never built)* was designed to send only the lease PDF and an extraction schema to the Anthropic API, never lead state, with no provider-side training opt-in. |
| Activity log | `contact_attempt` and `task` tables record who did what and when. |
| Secrets | Fly secrets in deployment. Never in the repo. |
| Pre-deploy review | Manual security review on every change that touches auth, multi-tenancy, or PII handling. |

### 3.3 The public read-only demo

[morphy-demo.fly.dev](https://morphy-demo.fly.dev) runs with `DEMO_MODE` on
([ADR-077](./adr/0077-read-only-demo-credential.md)). Anyone can press "Explore the demo" and get a
session for one read-only credential, with no password. The edge gate and per-request credential
check still apply, so removing that credential ends the demo's data access on the next fetch.

What a visitor can see and do:

- **Public-record parcel data.** Owner names, owner mailing addresses, and parcel details from the
  state and county sources in [NOTICE.md](../NOTICE.md). These are public records, but aggregated
  they meet most PII definitions (section 1). Takedown requests go through the GitHub issues listed
  in NOTICE.md.
- **No export.** The app has no CSV or bulk download feature, so the demo offers no way to pull
  owner names and addresses as a list. The static data files are only served to a signed-in
  session.
- **Seeded synthetic triage data only.** The demo board holds six fictional leads seeded by
  `python -m app.demo_seed` over government owners, never individuals or private businesses
  ([ADR-078](./adr/0078-demo-leads-over-government-owners.md)). Every note says it is
  fictional and every contact field is blank. No real outreach history is on the demo.
- **Writes are refused.** `current_principal` answers every non-GET/HEAD/OPTIONS request from a
  read-only principal with 403, including the password change. A test enumerates every write
  route to prove it.

---

## 4. Before sharing the product

Before showing the product to anyone:

1. **Refresh data** so nothing stale is on screen (see [DATA_FRESHNESS.md](./DATA_FRESHNESS.md)).
2. **Check screenshots** for individually identifiable owners. Prefer LLC and trust labels in any
   capture.
3. **Limit access to need-to-know.** Don't leave raw composite outputs or backend access in a
   shared drive afterward.
4. **If sharing a ZIP** (see [DEPLOYMENT.md](./DEPLOYMENT.md)): encrypt it with a strong password
   and send the password through a different channel than the file.
5. **If granting backend access:** `cd backend && python -m app.users add <username> <team>`
   prompts for a password and writes the `credential` table. To revoke, run
   `python -m app.users remove <username>`. It takes effect on that user's next request, with no
   restart ([ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md)). Rotating
   `AUTH_JWT_SECRET` also ends every live session at once.

---

## 5. Out of scope for Phase 1

Controls that larger-scale use would have needed, none of them built:

- **Per-tenant data residency** (region-locked storage).
- **Per-tenant at-rest encryption keys** (KMS or tenant-managed keys).
- **Activity log retention and export** for compliance review.
- **Versioned snapshot retention** for composite outputs (they are overwrite-only per
  [ADR-004](./adr/0004-current-only-versioning.md)).
- **A Data Processing Agreement (DPA)** with any partner who receives data.
- **A license re-check for MN parcels** (deferred per
  [ADR-018](./adr/0018-minnesota-deferred.md)) and any other ambiguous license terms.
- **A separate posture review before any skip-trace integration**, which would bring Fair Credit
  Reporting Act (FCRA)-adjacent custody obligations.

---

## 6. Incident response

If a sensitive output or backend session is exposed:

1. **Stop the exposure.** Remove the public URL, revoke the shared link, end the leaked session,
   or rotate the leaked credential.
2. **Document** the exposure window in the relevant commit message (date, scope, audience, what
   was visible). The git log is the record.
3. **Notify** anyone who received the exposed output.
4. **Rotate** every credential exposed alongside it: API keys, login passwords
   (`python -m app.users set-password`), and the `AUTH_JWT_SECRET` signing secret.
5. **Write a post-mortem:** what failure allowed this, and what control would have prevented it.

---

## 7. Compliance and legal posture

The project is **not** in scope for HIPAA, FedRAMP, SOX, or PCI. It works with data that is
public record field by field but PII once aggregated.

Frameworks that would apply to wider use:

- **Fair Credit Reporting Act (FCRA).** Not applicable as built. It becomes relevant if paid
  skip-trace is integrated ([ADR-057](./adr/0057-budget-posture-reframed.md)).
- **State data-broker registration.** Vermont and California keep registries. Likely to apply if
  the dataset were distributed.
- **GDPR / CCPA.** Not applicable unless the audience became international or primarily
  California-resident landowners.
- **CAN-SPAM.** Relevant only to mass email, which is a non-goal. It would require an
  unsubscribe link, an identified sender, and no deceptive subject lines.
