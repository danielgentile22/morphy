# SECURITY — Data Handling Posture

**Last updated:** 2026-05-20
**Owner:** project lead (single dev today).

This document records how we handle data that contains personally
identifying information (PII), what we treat as sensitive, and the
guardrails we maintain. Linked from ADR-040 + ADR-041 in
[DECISIONS.md](./DECISIONS.md).

This is **not** a comprehensive infosec policy. It's the
project-specific posture for a feasibility prototype that's about to
be shown to a partner / investor. Production-grade controls live in
the post-pitch roadmap.

---

## 1. What data we treat as sensitive

| Category | Examples | Why sensitive |
|---|---|---|
| **Parcel-owner PII** | Owner name + mailing address combined per parcel | Each field is public record individually; the *combination* (name + tied to a specific property + valuation + GPS location) meets most PII definitions |
| **Composite outputs** | `data/processed/composite/<fips>/parcels.*` | Contain parcel-owner PII at scale; aggregating amplifies sensitivity |
| **Pitch screenshots** | `docs/pitch-assets/*` | May show real owner names depending on capture context |
| **Anthropic API key** | `ANTHROPIC_API_KEY` | Standard secret hygiene |
| **AWS / Regrid credentials** | If user opts into paid Regrid | Standard secret hygiene |
| **Outputs shared with partners** | ZIP bundles per [DEPLOYMENT.md §5.2](./DEPLOYMENT.md) | Reduplicates PII outside our environment |

Public-record information that is **not** sensitive in isolation:
parcel APN, geometry, assessed value, FCC ASR records, EIA plant
data, distress-overlay polygons.

---

## 2. What we explicitly never do

1. **Never commit raw or composite data to git.** `data/` is
   git-ignored. Verify `.gitignore` includes `data/` and
   `data/processed/` before every push.
2. **Never publicly host composite outputs.** Hosted deployment
   requires access controls (deferred — see Section 5).
3. **Never share unencrypted ZIPs of composite data.** When shipping
   to a partner ([DEPLOYMENT.md §5.2](./DEPLOYMENT.md)), encrypt at
   rest and share via a secure channel.
4. **Never attempt LLC unmasking.** Resolving the human(s) behind a
   legal entity is a permanent non-goal (ADR-041). Display the raw
   entity string.
5. **Never store secrets in source code.** `.env` (git-ignored) or
   the OS keychain only.
6. **Never log full owner records in fetch.log or quality reports
   beyond aggregate counts.** Logs go to disk; we keep them succinct.

---

## 3. What we do today

| Control | Status | Where |
|---|---|---|
| `data/` git-ignored | ✅ enforced after Section 2.1 | `.gitignore` |
| GitHub repo visibility | **Private** (recommended) | Section 2.2 of work plan |
| Composite outputs encrypted at rest on disk | ❌ Not yet | macOS FileVault is the only protection today |
| Pitch screenshots audited for PII before sharing | ⚠ Manual | Recommendation: use AR (LLC-heavy) for demo captures |
| Anthropic key in env, not source | ✅ enforced | `.env` |
| No public hosted instance | ✅ enforced | Local-only deployment |
| No LLC unmasking pipeline | ✅ enforced | ADR-041 |

---

## 4. What we do at pitch time

Before each pitch / partner walkthrough:

1. **Refresh** the data so we're not pitching with stale info
   (per [DATA_FRESHNESS.md §5](./DATA_FRESHNESS.md)).
2. **Audit pitch-assets/** for any individually-identifiable owners.
   Prefer LLC / trust labels in screenshots.
3. **Confirm** the partner / audience has a need-to-know — don't
   leave raw composite outputs in a shared drive after the meeting.
4. **If sharing a ZIP** ([DEPLOYMENT.md §5.2](./DEPLOYMENT.md)):
   encrypt with a strong password; communicate password through a
   *different* channel than the file.

---

## 5. What's deferred (post-pitch)

For real outreach / hosted deployment we need:

- **Access controls on any hosted instance.** Cloudflare Access or
  AWS IAM; single-user initially, role-based later.
- **At-rest encryption** for composite outputs (cloud storage with
  KMS keys).
- **Audit log** of who accessed which composite when.
- **Retention policy** for older composites (currently overwrite-only
  per ADR-004; production may need versioned snapshots).
- **Data Processing Agreement (DPA)** with any partner who receives
  data, defining their handling obligations.
- **Re-evaluation of the MN parcels license** (currently deferred per
  ADR-018). Same for any other state with ambiguous license terms.

None of the above is in scope for the v1 pitch cut. All tracked in
[ROADMAP.md](./ROADMAP.md).

---

## 6. Incident response (such as it exists today)

If a sensitive output is exposed:

1. **Stop the bleed** — remove the public URL, revoke shared link, etc.
2. **Document** the exposure window in CHANGELOG.md (date, scope,
   audience, what was visible).
3. **Notify** affected partners if they received the exposed output.
4. **Rotate** any credential that was exposed alongside.

The audience for this is *very* small today (just the project lead),
but documenting the muscle now means it's already in place when the
team grows.

---

## 7. Compliance + legal posture

We are **not** subject to HIPAA, FedRAMP, SOX, or PCI scope. We are
working with data that is individually public-record but PII when
aggregated. Relevant frameworks to consult before any commercial
deployment:

- **Fair Credit Reporting Act (FCRA)** — N/A unless we begin furnishing
  data to credit decisions. Currently out of scope.
- **State-level data-broker registration** — Vermont, California
  have registries. Likely applies if we commercialize the dataset.
- **GDPR / CCPA** — N/A unless we expand internationally / serve
  CA-resident landowners as the primary audience. Track when scaling.

None of these block the pitch. All are tracked for the post-pitch
commercial-readiness review.

---

## 8. Owner of this posture

Whoever is currently driving the project. Today: a single dev. When
the team grows, this section names a specific role
(security@... or equivalent).
