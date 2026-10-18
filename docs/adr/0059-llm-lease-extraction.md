# ADR-059: LLM extraction approach for lease documents (Slice D+E)

**Status:** Accepted, **never built**. The design below was locked, but lease upload and extraction were never implemented before the project was archived. No extraction code, gold set or eval exists in the repo.
**Date:** 2026-05-25
**Pairs with:** ADR-053, ADR-055

## Context

Slice D+E was to add lease-document upload with structured field extraction (rent, escalation, expiry, amendment count, parties, and so on) plus per-field confidence. The per-slice gate set an 85% field-accuracy bar, which needs a real extraction pipeline.

The extraction loop also had a data reason: over time, uploaded leases would build a private comparables database that the public-data pipeline cannot match, because most recorded Memoranda of Lease redact the rent.

## Decision

**Model strategy:** **Sonnet 4.6 by default, with an Opus 4.7 retry** for leases the eval flags as low-confidence after the first pass. Haiku is too weak at long legal-document reasoning. Estimated cost was about $3 per lease on Sonnet and about $15 per lease for an Opus retry. Prompt caching cuts the cost of cached portions by about 80%.

**Confidence strategy:** **hybrid of citation-anchored and self-rated.**

- The model returns each field as `(value, page_number, verbatim_quote_from_source)`.
- Verifiable confidence: if `verbatim_quote` appears verbatim in the source PDF, confidence is high. The user can verify in one click ("show me where in the PDF this rent came from").
- Self-rated confidence is the fallback for inferred fields with no clean citation (for example "this is amendment 3 of 5", computed across pages).

**PDF handling:** **direct vision extraction.** Claude 4.x reads PDF pages as images natively. This avoids a separate OCR pipeline (Tesseract or AWS Textract), has fewer moving parts, and handles scanned legal documents (older recorded leases especially) better than OCR followed by text routing.

**Eval harness:** a **20-lease hand-labelled gold set**, built first. Field-level precision, recall and exact match per field. A **gating CI check** blocks a PR if any field's accuracy drops below 85%. A manual-override label covers intentional schema changes that need the gold set re-labelled.

## Consequences

- Per-lease cost is small (about $3 nominal, less with caching), well within the Phase 1 budget.
- Citation-anchored output gives the user a verification path instead of blind trust in the model.
- The 20-lease gold set is real ongoing work (about 8-10 hours to build, about 2 hours per eval re-run). It is the only way to know whether extraction quality is real.
- Schema design (which fields, what types, what is required) was left to the Slice D+E build, not fixed by this ADR.
- Rent data from each uploaded lease would feed the `lease_comp` table.

## Alternatives considered

- **Single model (Sonnet only).** Some leases are subtle enough to need an Opus retry, and the overhead is small (about 10% of cases). Rejected.
- **Self-rated confidence only.** LLMs systematically overrate their own confidence. Rejected.
- **Multi-pass consistency (3 runs at temperature 0.3, agreement as confidence).** Triples latency and cost without a matching accuracy gain over citation anchoring. Rejected.
- **Pre-OCR pipeline.** More infrastructure to maintain, and Claude vision handles scanned documents better than Tesseract. Rejected.
