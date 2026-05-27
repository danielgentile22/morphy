# STATUS — Where the project stands today

**Last updated:** 2026-05-25
**Updated by:** Phase 1 product pivot (ADRs 053–059 locked the decisions)
**Update cadence:** at the start of every slice and at every session handoff.

A snapshot of reality. If this disagrees with the code or data, the code/data wins — fix the doc.

---

## 0. 2026-05-25 pivot — pitch demo → Phase 1 product

The project reframed from "v1 pitch-quality demo across 4 states" to "Phase 1 of a fleshed-out co-founder-facing product." See [ADR-053](./adr/0053-product-phase-shift.md) and [SCOPE.md](./SCOPE.md).

**What carries forward unchanged** from the pitch-cut work:
- All v0–v3 work (data puller, preprocess framework, map app at `app/`, AR/MT remediation, schema work).
- Anchor states: AR + MT + FL + NC.
- Map app v2 stack (Svelte 5 + MapLibre + PMTiles + DuckDB-WASM) — Phase 1 layers new UI on top (Slices C + D).

**What changes:**
- Audience: investor walkthrough → co-founder daily use.
- Previously hard non-goals flip to in-scope: FCC ULS carriers, billboards on parcel, solar on parcel, lease doc upload + LLM extraction, triage state / write layer, free public-records contact enrichment.
- Old "Section 6 (testing)" and "Section 7 (pitch)" of the work plan are replaced by the Phase 1 slice plan with per-slice gates.
- ADR-006 (static-site) superseded by [ADR-055](./adr/0055-hosted-private-backend.md) for write-layer features (read-only analytical layers stay static).
- ADR-010 (free-only) reframed by [ADR-057](./adr/0057-budget-posture-reframed.md) as current-budget posture (paid unlocks expected post-Phase-1).
- ADR-041 (no LLC unmasking) narrowed to paid skip-trace + shell-piercing only (free SoS officer disclosure is in scope).

---

## 1. TL;DR

**Phase 1 next up:** Slice F — finish FL + NC composes. Requires the chunked compose (ADR-051, approved, not yet implemented) plus NC raw re-fetch.

| State | Raw data | Normalized | Composed | Notes |
|---|---|---|---|---|
| **AR** (05) | ✅ | ✅ 2,116,976 parcels | ✅ 11 joins, 8 views, 0 warnings | Audited clean 2026-05-21. |
| **MT** (30) | ✅ all 56 counties | ✅ 920,111 parcels | ✅ 11 joins, 8 views, 0 warnings | Audited clean 2026-05-21. |
| **FL** (12) | ✅ all 67 counties (~28 GB raw intact) | ❌ deleted 2026-05-20 | ❌ | Needs re-normalize + compose; chunked compose required first (§4.1). Slice F. |
| **NC** (37) | ❌ deleted 2026-05-20 | ❌ | ❌ | Needs full re-fetch from NC OneMap (§4.2). Slice F. |

Dropped from this cut: IN (18) and UT (49) — no owner data; MN (27) — license ambiguity.

---

## 2. What works

- **AR + MT end-to-end** — pull → normalize → compose → 8 views.
- The v3 preprocess framework, the puller, Git + CI.
- Map app at `app/` — Svelte 5 + MapLibre + PMTiles + DuckDB-WASM; reads catalog-driven composites for any composed state.
- **FL normalizer code** is correct and verified (geometry bug fixed; ADR-050 streaming per-county normalizer). The normalized output was deleted for disk space; re-running `python scripts/preprocess.py --state 12` will reproduce it once chunked compose is in place.

---

## 3. What does NOT work / is incomplete

| Item | Severity | Detail |
|---|---|---|
| FL normalized data | 🚫 Deleted | Deleted 2026-05-20 to free disk. Re-run normalizer when chunked compose is ready. |
| FL compose | 🚫 Blocked | Needs chunked compose (ADR-051) first, then re-normalize, then compose. §4.1 |
| NC raw data | 🚫 Deleted | Deleted 2026-05-20. Needs full re-fetch from NC OneMap when endpoint is stable. §4.2 |
| NC normalize + compose | 🚫 Blocked | Gated on NC re-fetch; will also need chunked compose. |
| Chunked compose | ⬜ To build | Approved (ADR-051); not started. Required for both FL and NC. **First task in Slice F.** |
| FCC ULS normalizers (carriers) | ⬜ Slice A | Raw data on disk (~5 GB across 6 bands). Phase 1 needs Cellular + PCS + AWS/700 (ADR-013 reverses for these). |
| Billboard + solar normalizers / joins | ⬜ Slice C | Raw on disk for FL/NC billboards; solar partial. ADR-014 partially reverses. |
| Backend (Postgres + S3 + FastAPI + auth) | ⬜ Slice D+E | Per [ADR-055](./adr/0055-hosted-private-backend.md). Tenant-shaped schema Day 1. |
| Lease doc upload + LLM extraction | ⬜ Slice D+E | Per [ADR-059](./adr/0059-llm-lease-extraction.md). 20-lease gold-set built first. |
| Tunable scoring UI | ⬜ Slice C | Per [ADR-058](./adr/0058-tunable-transparent-scoring.md). Client-side over DuckDB-WASM. |
| Vendor inference | ⬜ Slice B | ASR registrant + portfolio rollup. Lowest Phase 1 priority. |
| Tests (Slice 4 backend + LLM eval + multi-tenancy) | ⬜ | Per [TESTING.md §11](./TESTING.md). |

---

## 4. Known issues — detail

### 4.1 FL — normalized data deleted; chunked compose needed

FL's normalized output (~10.2 GB, 68 county parquet files, 11,184,113 parcels) was deleted 2026-05-20 to recover disk space. The raw FDOR NAL data is untouched at `data/raw/fdor_nal/current/` (~28 GB, all 67 counties).

Re-normalizing is straightforward — normalizer code is correct and verified. The blocker is composing: FL's 11.18M parcels require ~19.5 GB peak RAM and ~16–20 GB disk for the composite output, which exceeds the 16 GB dev machine. Fix: **chunked compose** (ADR-051) streaming county-by-county.

**To re-run FL end-to-end once chunked compose is built:**
```bash
python scripts/preprocess.py --state 12
```

### 4.2 NC — all raw data deleted; needs full re-fetch

Both `data/raw/nc_onemap_parcels/` (~8.3 GB, 1,106 of 1,186 MapServer pages) and `data/raw/NC/` (~958 MB) deleted 2026-05-20.

NC OneMap's auto-fetch paginates 1,186 pages (5,000 parcels each, ~5.9M total). The previous fetch stalled at page 1,106 on a server-side HTTP 504 at deep offsets — intermittent server degradation, not a code bug.

**To re-fetch NC:**
```bash
python -m app_puller   # use auto-fetch for nc_onemap_parcels
```
NC compose will also need chunked compose for the same memory reasons as FL.

NB: the puller's `prepare_fresh_partial()` wipes `.partial/` at start of every fetch → new fetch cannot resume from prior partial. Real resumability fix is a Slice F follow-up.

### 4.3 Remaining stale on-disk items

- `composite/18` and `normalized/in_parcels` — IN dropped from this cut (ADR-017); safe to delete.

---

## 5. Commit state

Section 5 + the Section 4 source rewrites + AR/MT data-quality remediation + doc updates committed once the **AR + MT audit was clean** (revised gate; the prior gate "after FL composes" was moot while FL is deferred behind chunked compose). `data/` is git-ignored — never commit raw or composite data.

This pivot's docs (this STATUS, SCOPE, GOALS, ROADMAP rewrites + 7 new ADRs + session summary + CONTEXT additions) commit as a single set documenting the 2026-05-25 phase shift.

---

## 6. Phase 1 slice progress

| Slice | State |
|---|---|
| **F** — Finish FL + NC composes | ⬜ Next up |
| **A** — FCC ULS carrier identification | ⬜ |
| **C** — Asset enrichment + tunable scoring UI | ⬜ |
| **D + E** — Lease docs + triage state + backend | ⬜ |
| **B** — Vendor inference | ⬜ |

Outcome bar: co-founder uses the product as his primary daily triage tool for 4 consecutive weeks (after Slice B ships). See [GOALS.md §3](./GOALS.md).

---

## 7. Outstanding decisions for the user

| Item | Notes |
|---|---|
| Chunked compose | Approved (ADR-051); implementation is Slice F first task. |
| Steel-in-the-Air free dataset — **premise overturned 2026-05-26** | The free county-level lease-rate dataset doesn't exist (per data-source research, `docs/research/reports-2026-05-26/INDEX.md`). Slice D `lease_comp` source-of-truth needs replacement — next-best free path is REIT 10-K rent disclosures + ABS securitization filings. Paid Steel-in-the-Air tier remains the Phase 2 unlock per [ADR-057](./adr/0057-budget-posture-reframed.md). |
| libpostal vs `usaddress` for owner-clustering address normalization | Slice 4 implementation detail. Lean libpostal; fall back to `usaddress` if dep-management is painful. |
| Hosting choice (Fly.io vs Render vs Hetzner) | Slice 4 implementation detail; any small VM works per [ADR-055](./adr/0055-hosted-private-backend.md). |
| First Slice F PR | Build the chunked compose. AR + MT regression-test (must produce identical output) before running on FL. |
