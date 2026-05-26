# ADR-059: LLM extraction approach for lease documents (Slice 4)

**Status:** Accepted
**Date:** 2026-05-25
**Pairs with:** ADR-053, ADR-055

## Context

Slice 4 (D + E) introduces lease-document upload with structured field extraction (rent, escalation, expiry, amendment count, parties, …) + per-field confidence. The 85% field-accuracy bar from the session per-slice gates needs an actual extraction pipeline.

The structured-extraction loop is the project's competitive moat — over time, uploaded leases build a private comparables DB that the public-data pipeline can never match (most recorded Memoranda of Lease redact rent).

## Decision

**Model strategy:** **Sonnet 4.6 default + Opus 4.7 retry path** for leases the eval flags as low-confidence after the first pass. Haiku is too weak on long legal-document reasoning. Cost: ~$3 / lease Sonnet, ~$15 / lease Opus retry. With prompt caching enabled, per-lease cost drops ~80% on cached portions.

**Confidence strategy:** **Hybrid citation-anchored + self-rated.**

- Model returns each field as `(value, page_number, verbatim_quote_from_source)`.
- Verifiable confidence: if `verbatim_quote` appears verbatim in source PDF, confidence is high. Co-founder one-click verifies (*"show me where in the PDF this rent came from"*).
- Self-rated confidence as fallback for genuinely inferred fields (e.g. *"this is amendment 3 of 5"* computed across pages) where there's no clean citation.

**PDF handling:** **Direct vision extraction.** Claude 4.x reads PDF pages as images natively. Avoids running a separate OCR pipeline (Tesseract / AWS Textract); fewer moving parts; handles scanned legal docs (older recorded leases especially) better than OCR + text routing.

**Eval harness:** **20-lease hand-labelled gold-set** built first. Field-level precision / recall / exact-match per field. **Gating CI check** — PR blocks if any field's accuracy drops below 85%. Manual-override label for cases where the schema is intentionally changed and the gold-set needs re-labelling.

**At build time:** use the `claude-api` skill (handles prompt caching, Tool use schema, Sonnet/Opus selection).

## Consequences

- Per-lease cost is small (~$3 nominal, less with caching) — well within Phase 1 budget.
- Citation-anchored output gives the co-founder a verification path; he doesn't trust the model blindly.
- The 20-lease gold-set is real ongoing work (~8–10 hrs to build, ~2 hrs per eval re-run). The only way to know if extraction quality is real.
- Schema design (which fields, what types, what's required) gets defined inside Slice 4 — not constrained by this ADR.
- Per-uploaded-lease rent data augments the `lease_comp` table (see session summary §Comparables).

## Alternatives considered

- **Single-model (Sonnet only):** some leases are subtle enough to warrant Opus retry; cost overhead small (~10% of cases). Rejected.
- **Self-rated confidence only:** LLMs systematically overrate own confidence. Rejected.
- **Multi-pass consistency (3× temp 0.3, agreement = confidence):** too expensive (3× latency + cost) without proportional accuracy gain over citation-anchored. Rejected.
- **Pre-OCR pipeline:** more infra to maintain; Claude vision handles scanned docs better than Tesseract anyway. Rejected.
