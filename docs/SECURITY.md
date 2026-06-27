# SECURITY — Data Handling Posture

**Last updated:** 2026-06-26
**Owner:** project lead (single dev today).

This document records how we handle data that contains personally identifying information (PII), what we treat as sensitive, and the guardrails we maintain. Linked from ADR-040 + ADR-041 (narrowed by ADR-057) in [DECISIONS.md](./DECISIONS.md).

This is **not** a comprehensive infosec policy. It's the project-specific posture for a 2-person team running a co-founder-facing product on free-tier hosting. Production-grade controls live in the post-Phase-1 roadmap.

---

## 1. What data we treat as sensitive

| Category | Examples | Why sensitive |
|---|---|---|
| **Parcel-owner PII** | Owner name + mailing address combined per parcel | Each field is public record individually; the *combination* (name + tied to a specific property + valuation + GPS location) meets most PII definitions |
| **Composite outputs** | `data/processed/composite/<fips>/parcels.*` | Contain parcel-owner PII at scale; aggregating amplifies sensitivity |
| **Uploaded lease documents** (Slice D+E, unbuilt) | PDFs in S3-compatible object store | Contain owner identity + rent terms + carrier identity; landowner-signed contracts |
| **LLM-extracted lease fields** (Slice D+E, unbuilt) | `lease.extracted_fields_json` + denormalized rent/escalation/expiry | Same sensitivity as the underlying PDF |
| **Lead state + activity log** | `lead.*`, `contact_attempt.*`, `task.*`, `ask_log.*` | Reveals which landowners the co-founder is targeting + the negotiation status |
| **Free SoS officer disclosure surfaces** (Slice D+E, unbuilt) | Cached LLC-officer lookups in the lead-detail panel | Public records but cached / aggregated alongside lead state |
| **Pitch / demo screenshots** | `docs/pitch-assets/*` | May show real owner names depending on capture context |
| **Anthropic API key** | `ANTHROPIC_API_KEY` (`scripts/diagnose.py` + Ask Claude SSE `POST /api/audit/ask` — deployed but DORMANT until the Fly secret is set; + future D+E lease extraction) | Standard secret hygiene |
| **AWS / S3-compatible / hosting credentials** | live backend hosting (Fly / R2 / Cloudflare) + (future) lease-PDF object store + (future) paid Regrid | Standard secret hygiene |
| **Login credentials + session JWTs** | `credential`-table password hashes in the app DB (never committed; commit-guard test) + HS256 session tokens in httpOnly cookies ([ADR-062](./adr/0062-username-password-replaces-magic-link.md) / [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md) / [ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)) | Auth surface — leakage = account takeover |
| **Tenant boundary** | `tenant_id` column on every backend table; every route filters by it | Teams ARE tenants (resolved per request — no `tenant_id=1` stub); the boundary must hold so no tenant sees another's leads |
| **Outputs shared with partners** | ZIP bundles per [DEPLOYMENT.md §5.2](./DEPLOYMENT.md) | Reduplicates PII outside our environment |

Public-record information that is **not** sensitive in isolation: parcel APN, geometry, assessed value, FCC ASR records, EIA plant data, distress-overlay polygons.

---

## 2. What we explicitly never do

1. **Never commit raw or composite data to git.** `data/` is git-ignored. Verify `.gitignore` includes `data/` and `data/processed/` before every push.
2. **Never commit uploaded lease PDFs.** They live in S3-compatible storage only.
3. **Never publicly host composite outputs or the backend.** Hosted-private only ([ADR-055](./adr/0055-hosted-private-backend.md)) — access controls enforced; the data plane (`/data/processed/*`) is edge-gated through the same auth ([ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)).
4. **Never share unencrypted ZIPs of composite data.** When shipping to a partner ([DEPLOYMENT.md §5.2](./DEPLOYMENT.md)), encrypt at rest and share via a secure channel.
5. **Never attempt paid LLC unmasking / shell-piercing / identity resolution.** Permanent non-goal per ADR-041 (narrowed by [ADR-057](./adr/0057-budget-posture-reframed.md)). **In scope:** free public-records officer disclosure (SoS business-entity lookups, UCC-1 filings) — these surface officers the entity *itself* publicly discloses; not identity resolution.
6. **Never store secrets in source code.** `.env` (git-ignored) or the OS keychain only. In the backend: environment variables in the host platform's secret store (Fly secrets).
7. **Never serve uploaded lease PDFs from a public URL.** S3-compatible storage with **signed download URLs only**, scoped to the requesting user's tenant.
8. **Never leak cross-tenant data.** Every backend route must filter by `tenant_id`; multi-tenancy isolation tests run on every PR (see [TESTING.md](./TESTING.md)).
9. **Never log full owner records, lease terms, or extracted fields beyond aggregate counts** in app logs.

---

## 3. What we do today

### 3.1 Data layer (current)

| Control | Status | Where |
|---|---|---|
| `data/` git-ignored | ✅ enforced | `.gitignore` |
| GitHub repo visibility | **Private** | `danielgentile22/infra-lease-analytics` |
| Composite outputs encrypted at rest on disk | ❌ Not yet | macOS FileVault is the only protection today |
| Pitch / demo screenshots audited for PII before sharing | ⚠ Manual | Prefer LLC-heavy AR for demo captures |
| Anthropic key in env, not source | ✅ enforced | `.env` |
| Composite data plane gated behind auth | ✅ live in prod | `/data/processed/*` edge-gated via `forward_auth` ([ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)) — the app is hosted-private, not public |
| No LLC unmasking pipeline | ✅ enforced | ADR-041 / ADR-057 |

### 3.2 Backend layer (live in production)

The backend is deployed in production ([ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md)) — auth, multi-tenancy, hosting, and the audit stream below have **shipped**. Only lease-PDF storage + LLM lease extraction (the rest of D+E, [ADR-059](./adr/0059-llm-lease-extraction.md)) remain unbuilt; those rows are marked accordingly.

| Control | Posture |
|---|---|
| Auth | Username/password against the `credential` table in the app DB (PBKDF2 hashes, managed via `python -m app.users`); identity-only HS256 session JWTs in an httpOnly `pilot_session` cookie; **the credential table is authoritative on every request** — removal / re-teaming applies on the next click, and the edge gates `/data/processed/*` through the same check ([ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md) as amended by [ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)) |
| Multi-tenancy | `tenant_id` column on every table; every route filters by it; teams ARE tenants (no `tenant_id=1` stub); isolation tests gate PRs |
| Lease-PDF storage *(unbuilt — rest of D+E)* | S3-compatible bucket; **encrypted at rest** (SSE-S3 or KMS); private bucket; signed download URLs only |
| Database | SQLite-on-volume in prod, replicated to R2 via Litestream ([ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md)); DB-agnostic ORM (Postgres-ready). TLS in transit; continuous backup |
| API transport | HTTPS only (HSTS); HTTP redirects to HTTPS (Cloudflare orange / Full-strict) |
| LLM calls | Anthropic API only; no provider-side training opt-in; minimum data sent. Ask Claude (catalog helper, `POST /api/audit/ask`) sends only catalog context; lease extraction *(unbuilt)* will send the lease PDF + an extraction schema, not lead state |
| Audit log | `contact_attempt` + `task` + `ask_log` tables record who did what when (outreach attempts, tasks, LLM-helper calls) |
| Secrets | Host platform secret manager (Fly secrets). Never in repo. |
| Pre-deploy review | Manual security-review skill on every PR that touches auth, multi-tenancy, or PII handling |

---

## 4. What we do at slice / pitch time

Before sharing the product with anyone (co-founder, prospective hire, advisor):

1. **Refresh data** so we're not showing stale info (per [DATA_FRESHNESS.md §5](./DATA_FRESHNESS.md)).
2. **Audit screenshots** for individually-identifiable owners. Prefer LLC / trust labels in any capture.
3. **Confirm need-to-know.** Don't leave raw composite outputs or backend access in a shared drive after the meeting.
4. **If sharing a ZIP** ([DEPLOYMENT.md §5.2](./DEPLOYMENT.md)): encrypt with a strong password; communicate password through a *different* channel than the file.
5. **If granting backend access**: `cd backend && python -m app.users add <username> <team>` (prompts for a password, writes the `credential` table). To revoke: `python -m app.users remove <username>` — effective on their next request, no restart ([ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md)). Rotating `AUTH_JWT_SECRET` additionally kills every live session at once.

---

## 5. What's deferred (Phase 2+ and beyond)

For larger-scale outreach / true multi-tenant sale we'll need:

- **Per-tenant data residency** (a future paying customer may demand region-locked storage).
- **At-rest encryption keys per tenant** (KMS / customer-managed keys).
- **Audit log retention + export** for compliance review.
- **Versioned snapshot retention** for composite outputs (currently overwrite-only per ADR-004).
- **Data Processing Agreement (DPA)** with any partner who receives data.
- **Re-evaluation of MN parcels license** (currently deferred per ADR-018) and any other ambiguous license terms.
- **Skip-trace integration** (if/when ADR-057 unlocks paid contact data) brings FCRA-adjacent custody implications — needs a separate posture review before it ships.

None of the above is in scope for Phase 1. All tracked in [ROADMAP.md](./ROADMAP.md).

---

## 6. Incident response (such as it exists today)

If a sensitive output or backend session is exposed:

1. **Stop the bleed** — remove the public URL, revoke shared link, kill the leaked session, rotate the leaked credential, etc.
2. **Document** the exposure window in the relevant commit message (date, scope, audience, what was visible) — git log is the canonical history.
3. **Notify** affected partners if they received the exposed output.
4. **Rotate** any credential that was exposed alongside (API keys, login passwords — `python -m app.users set-password` — and the `AUTH_JWT_SECRET` signing secret).
5. **Post-mortem** — what failure mode allowed this; what control would have prevented it.

The audience for this is *very* small today (the project lead + the co-founder), but documenting the muscle now means it's already in place when the team grows.

---

## 7. Compliance + legal posture

We are **not** subject to HIPAA, FedRAMP, SOX, or PCI scope. We are working with data that is individually public-record but PII when aggregated.

Relevant frameworks to consult before any commercial deployment:

- **Fair Credit Reporting Act (FCRA)** — N/A today. **Becomes relevant** if and when paid skip-trace integrates (Phase 2+ per [ADR-057](./adr/0057-budget-posture-reframed.md)).
- **State-level data-broker registration** — Vermont, California have registries. Likely applies if we commercialize the dataset.
- **GDPR / CCPA** — N/A unless we expand internationally / serve CA-resident landowners as the primary audience. Track when scaling.
- **CAN-SPAM** — relevant when Phase 2 mass-email lands. Mandatory: unsubscribe link, identifying sender, no deceptive subjects. Slice in scope at that point.

None of these block Phase 1. All tracked for the post-Phase-1 commercial-readiness review.

---

## 8. Owner of this posture

Whoever is currently driving the project. Today: a single dev (user) + the co-founder as primary product user. When the team grows, this section names a specific role (security@... or equivalent).
