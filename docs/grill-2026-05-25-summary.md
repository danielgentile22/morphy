# Grill session — 2026-05-25

Comprehensive record of the `/grill-with-docs` session that produced the Phase 1 product pivot. The 7 new ADRs (053–059) live in `docs/adr/`; this memo captures the lower-bar decisions, the trail of questions/answers, and context that doesn't fit in an ADR.

**Session shape:** 16 substantive grill rounds (Q1–Q16) + Q17 wrap-up. User in flow with terse answers; mostly accepted recommended options. Driven by the user's request: *"I want to review every decision made so far. General product choices, specifics of the implementation, and everything in between. I want to review plans for the future and all the documentation."*

---

## The pivot in one paragraph

The project was a "v1 pitch-quality demo across 4 anchor states" oriented to investor walkthrough. The user reframed: *"We're past v1. I need this to be a fully fleshed-out product at this point."* The co-founder (business side of the 2-person team) becomes the *user* of the product, opening it daily to triage cell-tower ground-lease renegotiation candidates. Previously-deferred features (FCC ULS carriers, billboards/solar enrichment, lease document upload + LLM extraction, triage write layer, SoS officer lookups, free comparables) flipped to in-scope; rooftop installations defer to Phase 2.

---

## What got an ADR

| ADR | Lock |
|---|---|
| [053](./adr/0053-product-phase-shift.md) | Pitch demo → co-founder-facing product. Outcome bar = primary daily tool for 4 consecutive weeks. |
| [054](./adr/0054-asset-universe-phase-1-2.md) | Phase 1 = freestanding towers only; Phase 2 = rooftops. Rooftop-flavoured cofounder asks defer with rooftops. |
| [055](./adr/0055-hosted-private-backend.md) | Hosted-private backend with tenant-shaped schema Day 1. Supersedes ADR-006 (static-site) for write-layer features. |
| [056](./adr/0056-lead-equals-owner-cluster.md) | Triage primitive = owner-cluster, not parcel. Rollup `max + 0.1·log(parcel_count)`. ADR-024 strengthened with conservative normalization + manual merge/split UI. |
| [057](./adr/0057-budget-posture-reframed.md) | ADR-010 reframes from "permanent stance" to "current budget." ADR-041 narrows to paid skip-trace + shell-piercing only — free SoS / UCC-1 in scope. |
| [058](./adr/0058-tunable-transparent-scoring.md) | Client-side tunable scoring with profiles, ships Slice 3. Lease-derived signals plug in after Slice 4. |
| [059](./adr/0059-llm-lease-extraction.md) | Sonnet 4.6 default + Opus 4.7 retry; hybrid citation + self-rated confidence; direct-vision PDFs; 20-lease gold-set; gating CI check. |

---

## Phase 1 slice plan (untimed)

1. **F** — Finish FL + NC composes (chunked compose ADR-051 + NC re-fetch)
2. **A** — FCC ULS carrier identification (Cellular Part 22 + PCS Part 24 + AWS / 700 MHz Part 27)
3. **C** — Asset enrichment (billboards + solar on parcel) + tunable scoring UI
4. **D + E** — Lease doc upload + LLM extraction + triage state / write layer / CSV exports (backend stands up here)
5. **B** — Vendor (tower-co) inference

Per-slice "shipped" gates in `docs/GOALS.md §3`. Overall outcome bar: co-founder uses the product as his primary daily triage tool for 4 consecutive weeks.

---

## Below-the-ADR-bar decisions

### Comparables (Q9)

**Strategy:** **(β) bootstrap from Steel-in-the-Air free county-level rent benchmarks** (~3000 counties seed). Augment with uploaded-lease granular data over time. Paid Steel-in-the-Air tier is a Phase 2 unlock.

**Data model:** `lease_comp(state, county, asset_type, source, year, rent_mean, rent_p25, rent_p75, sample_size)`. Bootstrap = one-time normalizer + small table; lives next to lease data in Slice 4. UI: *"this tower's rent is in the Nth percentile vs {county / region}."*

### Contact-data path (Q5)

**Option (b):** free public-records enrichment baked into the lead-detail panel — one-click Secretary of State business-entity lookup per state, surfaced UCC-1 filings, snail-mail letter template generator. Co-founder does any remaining research per lead. Adds ~1 week to Slice 4. **Permanently out:** paid skip-trace (Whitepages Pro, Cole Information, IDI, Pipl), aggressive identity-resolution. See [ADR-057](./adr/0057-budget-posture-reframed.md).

### Lead + lease state models (Q11)

**Lead states** (on `owner_cluster_id`):

```
new → flagged → contacted → talking → {won | lost | passed}
                                  ↓
                          re_engage_later (timed; auto-returns to flagged)
```

**Lease states** (on `(parcel_id, tower_asr_id, carrier_callsign)`):

```
unknown → pending_upload → uploaded → extracted → verified
                                              ↓
                                          superseded (amendment)
```

**Tables (Slice 4 data model):**

```
lead(tenant_id, owner_cluster_id, state, priority_score,
     latest_note, owner_user_id, updated_at)

lease(tenant_id, parcel_id, tower_asr_id, carrier_callsign, state,
      pdf_object_key, extracted_fields_json, extraction_confidence_json,
      verified_at, monthly_rent_cents, escalation_pct, expiry_date,
      amendment_count, parties_text)

activity(tenant_id, entity_type, entity_id, timestamp, user_id,
         action, content_md)

owner_cluster_override(tenant_id, source_cluster_id, target_cluster_id)
```

Activity log carries history for both leads and leases (no separate `*_history` tables). Extracted fields denormalized onto `lease` for query speed; original raw JSON sits alongside for re-extraction.

### ULS↔ASR join (Q13)

**Strategy (γ) hybrid:** ASR-number cross-reference where ULS has it; spatial-proximity fallback elsewhere with confidence tag (`verified` = cross-ref; `likely` ≤ 100 m; `possible` 100–500 m). Tag shows in lead-detail panel.

**Bands:** Cellular (Part 22) + PCS (Part 24) + AWS / 700 MHz (Part 27). Microwave, Ownership, Transfers, Leasing remain deferred.

**Carrier rollup:** `callsign → carrier_name` mapping from ULS `HD.entity_name`, normalized to top ~10 entities (~95% of US wireless). Hand-maintained list for the tail.

**Data audit at Slice A kickoff:** sample 1000 Cellular `LO` records, count populated `asr_number`. If <30%, tighten the spatial-proximity tolerance.

### Testing additions for Slice 4 (Q14)

Extending `docs/TESTING.md` for the new backend + LLM + multi-tenancy surface:

| Surface | Tool | Notes |
|---|---|---|
| Backend HTTP API | pytest + testcontainers-postgres | Real Postgres; auth flow; lead/lease CRUD; activity-log append. |
| Multi-tenancy isolation | pytest fixtures with 2 synthetic tenants | Write tests even with 1 real tenant — stay correct when a second joins. |
| LLM extraction eval | gold-set runner as separate CI job | 20-lease hand-labelled. Field-level precision / recall / exact-match. **Gating PR check** — blocks if any field accuracy drops below 85%. Manual-override label for intentional schema changes. |
| Data audits | bash + python checks post-compose | Zero warnings, expected join count, no missing canonical columns. Block merge if a state breaks. |

**Per-slice test-coverage bar:** ≥ 70% line coverage of new code shipped in each slice.

### Owner-cluster strengthening (Q15)

Layered normalization (in order, all conservative):

1. Suffix stripping (LLC, INC, CORP, LTD, TRUST, JR, SR, II, III, etc.)
2. Personal-name token sort (`"JOHN A SMITH" ≡ "SMITH JOHN A"`)
3. Trust / estate normalization (`"X FAMILY TRUST" ≡ "X FAMILY LIVING TRUST" → "X FAMILY"`)
4. USPS address standardization (libpostal preferred; fall back to `usaddress`)

**Phonetic name match (Soundex / metaphone) explicitly excluded** — biases toward false merges (wrong-person calls), worse for a cold-call business than false splits (duplicate calls).

**Manual merge/split UI in Slice 4 lead-detail panel.** Overrides in `owner_cluster_override(tenant_id, source_cluster_id, target_cluster_id)`. Raw cluster IDs stay in parquet (composites don't regenerate per merge); backend computes `display_cluster_id = coalesce(override_target, raw_cluster_id)`.

### Data freshness UX (Q16)

**Surfaces:**

- Top of triage list: *"Last full data refresh: AR 12d, MT 9d, FL 47d, NC 21d"*
- Per-lead detail panel: *"Parcel data from {date}; tower data from {date}; lease comp data from {date}"*
- Per-source admin view (gated): refresh-trigger button (Phase 2 self-serve)

**Staleness policy:** information-only for most sources. Hard banner when a state's parcel source is > 180 days old. ULS staleness = soft warning. Distress overlays = soft warning.

**Refresh trigger:** dev-only Phase 1 (you run the puller). Self-serve refresh from the product is Phase 2.

**Painful reality:** MANUAL_ONLY sources (FDOR NAL = 67 Florida counties, click-through each) need *you* at every refresh. Phase 1 doesn't fix this. Phase 2 candidates: guided checklist UI in the puller, or paid bulk-data unlocks.

---

## Glossary additions (already in `CONTEXT.md`)

- **Registrant** — entity on FCC ASR `EN.dat`. Often original builder, frequently sold since. Distinct from Vendor.
- **Vendor** — current tower-co owner (Crown Castle, ATC, SBA, Vertical Bridge). Not in any free dataset directly.
- **Carrier** — wireless service (AT&T, Verizon, T-Mobile, Dish) renting space from Vendor. Sourced from FCC ULS.
- **Freestanding tower** — standalone monopole/lattice/guyed ≥ 200 ft, ASR-registered. Phase 1 primary asset.
- **Rooftop installation** — antenna/DAS on a commercial building. Mostly absent from ASR. Phase 2.
- **Triage** — the co-founder's working session inside the product. Phase 1 primary user-flow.

---

## Q&A trail (bullet summary)

- **Q1** — Project shape: pitch demo → product. User explicit: *"past v1."*
- **Q2** — Co-founder workflow walkthrough (he provided detailed wishlist).
- **Q3** — Asset universe: **(c) Towers Phase 1, rooftops Phase 2.**
- **Q4** — Slice ordering: **F → A → C → D+E → B**, untimed.
- **Q5** — Contact data: **(b) free public-records enrichment**. ADR-010 reframes; ADR-041 narrows.
- **Q6** — Scoring: **(γ) tunable + transparent**, ships Slice 3, hook for lease signals after Slice 4.
- **Q7** — Per-slice quantitative gates locked; outcome bar = primary daily tool for 4 weeks.
- **Q8** — Deployment: **hosted-private + tenant-shaped schema Day 1**.
- **Q9** — Comparables: **(β) bootstrap from Steel-in-the-Air free**; paid tier later.
- **Q10** — Triage primitive: **(β) lead = owner-cluster**. Rollup = `max + 0.1·log(parcel_count)`. ADR-024 strengthened in Slice 4.
- **Q11** — Lead + lease state machines + 3-table data model accepted as proposed.
- **Q12** — LLM extraction: **Sonnet + Opus retry, hybrid citation + self-rated, direct-vision PDFs**.
- **Q13** — ULS↔ASR join: **(γ) hybrid cross-ref + spatial fallback**. Cellular + PCS + AWS / 700.
- **Q14** — Testing additions for backend + LLM + multi-tenancy, gated LLM eval CI check.
- **Q15** — Owner-cluster: conservative normalization layers 1–4 + manual merge/split UI (no phonetic match).
- **Q16** — Data freshness UX: information-only + 180-day hard banner; dev-only refresh Phase 1.
- **Q17** — Wrap-up: option (β) — full ADRs + doc rewrites + memory + this memo.

---

## Open items that surfaced but weren't fully resolved

- **Steel-in-the-Air download URL / format** — Slice D needs confirmation of how to ingest their free county-level tier.
- **libpostal vs `usaddress`** for address normalization — Slice 4 implementation pick depending on dep-management friction.
- **Hosting vendor** (Fly.io vs Render vs Hetzner) — Slice 4 implementation detail; any small VM works.
- **The `claude-api` skill** is available and triggers when actually building Slice 4 — handles prompt caching, Tool use, model selection.
- **First Slice F PR plan:** build chunked compose, regression-test against AR + MT (must produce identical output), then run on FL.
