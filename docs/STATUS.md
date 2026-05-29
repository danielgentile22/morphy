# STATUS — Where the project stands today

**Last updated:** 2026-05-29
**Updated by:** Phase 1 product pivot (ADRs 053–059 locked the decisions); 2026-05-29 audit-remediation pass — FL **recomposed** (county-score gap **closed**: 11 joins, `county_scores` layer + tower/solar county-score joins now present; consistent with AR/MT); merged to `main` 2026-05-29 and reconciled the issue tracker (closed #9 chunked compose, #20 FL compose, #14 solar join)
**Update cadence:** at the start of every slice and at every session handoff.

A snapshot of reality. If this disagrees with the code or data, the code/data wins — fix the doc.

---

## 0. 2026-05-25 pivot — pitch demo → Phase 1 product

The project reframed from "v1 pitch-quality demo across 4 states" to "Phase 1 of a fleshed-out co-founder-facing product." See [ADR-053](./adr/0053-product-phase-shift.md) and [SCOPE.md](./SCOPE.md).

**What carries forward unchanged** from the pitch-cut work:
- All v0–v3 work (data puller, preprocess framework, map app at `app/`, AR/MT remediation, schema work).
- Anchor states: AR + MT + FL (NC deferred — see §4.2).
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

**Phase 1 next up:** Slice A (carriers) — Slice F's committed-anchor composes are complete. The three committed anchors (AR + MT + FL) are all composed and mutually consistent. Chunked compose (ADR-051) shipped 2026-05-19. **FL was recomposed 2026-05-29** and is live in the app (`index.json` lists 05, 12, 30); the earlier county-score gap is **closed** — FL now carries the `county_scores` layer and ran all 11 joins, including `CountyScoreToTowerJoin` + `CountyScoreToSolarJoin` (§4.1). NC (37) remains **deferred / a Phase-1 stretch** — its re-fetch + compose is not a committed Slice-F deliverable (§4.2). (Audit remediation + FL recompose merged to `main` 2026-05-29 — see §5.)

| State | Raw data | Normalized | Composed | Notes |
|---|---|---|---|---|
| **AR** (05) | ✅ | ✅ 2,116,976 parcels | ✅ 11 joins, 8 views, 0 warnings | Audited clean 2026-05-21. |
| **MT** (30) | ✅ all 56 counties | ✅ 920,111 parcels | ✅ 11 joins, 8 views, 0 warnings | Audited clean 2026-05-21. |
| **FL** (12) | ✅ all 67 counties (~28 GB raw intact) | ✅ 11,184,113 parcels (fdor_nal) | ✅ recomposed 2026-05-29 — 11,425,608 parcels, 11 joins, 8 views, 0 warnings | Live in app. County-score gap **closed** 2026-05-29: `county_scores` layer + tower/solar county-score joins now present; consistent with AR/MT (§4.1). |
| **NC** (37) | ❌ deleted 2026-05-20 | ❌ | ❌ | ⏸️ Deferred / Phase-1 stretch — re-fetch from NC OneMap (504s) + normalize + compose deferred, not a committed anchor (§4.2). |

Three committed anchors: AR + MT + FL. Dropped entirely from this cut: IN (18) and UT (49) — no owner data; MN (27) — license ambiguity.

---

## 2. What works

- **AR + MT + FL end-to-end** — pull → normalize → compose → 8 views. FL was re-normalized 2026-05-26 and **recomposed 2026-05-29** (11,425,608 parcels, 11 joins, county-score gap closed) and is live in the app.
- The v3 preprocess framework, the puller, Git + CI.
- Map app at `app/` — Svelte 5 + MapLibre + PMTiles + DuckDB-WASM; reads catalog-driven composites for any composed state.
- **FL normalizer code** is correct and verified (geometry bug fixed; ADR-050 streaming per-county normalizer). FL re-normalized + composed successfully on 2026-05-26 via the chunked path (ADR-051); re-running `python scripts/preprocess.py --state 12` reproduces it.
- **Chunked compose** (ADR-051) — memory-bounded per-county streaming Composer; the only compose path now (single-shot retired 2026-05-27). Closed #9.
- **Solar→parcel enrichment** — `SolarToParcelJoin` combines USPVDB polygons + EIA-860 points (both normalize to the `solar_facility` type); `has_solar` / `solar_count` populated on parcels in AR/MT/FL, covered by `tests/test_infra_to_parcel.py`. Closed #14.

---

## 3. What does NOT work / is incomplete

| Item | Severity | Detail |
|---|---|---|
| NC raw data | ⏸️ Deferred | Deleted 2026-05-20. Re-fetch from NC OneMap deferred to a Phase-1 stretch (endpoint intermittently 504s). Not a committed Slice-F deliverable. §4.2 |
| NC normalize + compose | ⏸️ Deferred | Follows the deferred NC re-fetch — future stretch, not gating. |
| FCC ULS normalizers (carriers) | ⬜ Slice A | Raw data on disk (~5 GB across 6 bands). Phase 1 needs Cellular + PCS + AWS/700 (ADR-013 reverses for these). |
| Billboards normalizer + join | 🟡 Slice C (partial) | `fdot_/ncdot_/txdot_billboards` normalizers + `BillboardToParcelJoin` are registered and emit `has_billboard`/`billboard_count`, but billboard raw isn't populated for the anchors (FL composed the join as a no-op) and there are no tests yet (#13). ADR-014 partially reverses. *(Solar join is done — see §2, #14.)* |
| Backend (Postgres + S3 + FastAPI + auth) | ⬜ Slice D+E | Per [ADR-055](./adr/0055-hosted-private-backend.md). Tenant-shaped schema Day 1. |
| Lease doc upload + LLM extraction | ⬜ Slice D+E | Per [ADR-059](./adr/0059-llm-lease-extraction.md). 20-lease gold-set built first. |
| Tunable scoring UI | ⬜ Slice C | Per [ADR-058](./adr/0058-tunable-transparent-scoring.md). Client-side over DuckDB-WASM. |
| Vendor inference | ⬜ Slice B | ASR registrant + portfolio rollup. Lowest Phase 1 priority. |
| Tests (Slice 4 backend + LLM eval + multi-tenancy) | ⬜ | Per [TESTING.md §11](./TESTING.md). |

---

## 4. Known issues — detail

### 4.1 FL — recomposed 2026-05-29; county-score gap closed

FL was recomposed on 2026-05-29 (`composite/12/summary.json` dated 2026-05-29): 11,425,608 parcels, **11 joins applied (0 skipped)**, 8 views, pmtiles, 0 warnings. It is live in the app (`index.json` lists 05, 12, 30). The raw FDOR NAL data remains at `data/raw/fdor_nal/current/` (~28 GB, all 67 counties). Composing succeeded via the **chunked compose** path (ADR-051), which keeps peak memory bounded so FL's parcels fit on the 16 GB dev machine. (The 11,425,608 composed count = `fdor_nal` canonical 11,184,113 + `fl_fgdl_parcels` ~241,518; both FL parcel sources are composed.)

**Gap closed (FL now consistent with AR/MT):** the earlier compose (2026-05-26) had **no `county_scores` catalog layer** and **skipped `CountyScoreToTowerJoin` + `CountyScoreToSolarJoin`** because it ran before the `arc_distressed` / `usda_persistent_poverty` normalizers finished, so county-score data wasn't loaded at compose time. The 2026-05-29 recompose ran with that data present: FL now carries the standalone `county_scores` layer and both county-score joins. (The recompose also surfaced and fixed a pre-existing `safe_merge` suffix-collision bug in `apply_county_score` that crashed once FL had county-score data — see the audit remediation.) To reproduce:
```bash
python scripts/preprocess.py --state 12
```

**Per-state join status (as composed):**

| Join | AR (05) | MT (30) | FL (12) |
|---|---|---|---|
| `BillboardToParcelJoin` | skipped | skipped | ran as no-op (no billboard raw → all `has_billboard=false`) |
| `CountyScoreToTowerJoin` | applied | applied | **applied** (2026-05-29) |
| `CountyScoreToSolarJoin` | applied | applied | **applied** (2026-05-29) |
| standalone `county_scores` layer | present | present | **present** (2026-05-29) |

### 4.2 NC — deferred / Phase-1 stretch (raw deleted; re-fetch deferred)

NC is **deferred to a Phase-1 stretch** — no longer a committed anchor (see [SCOPE.md §2](./SCOPE.md)). The history and a path back are preserved here for when it's picked up.

Both `data/raw/nc_onemap_parcels/` (~8.3 GB, 1,106 of 1,186 MapServer pages) and `data/raw/NC/` (~958 MB) deleted 2026-05-20.

NC OneMap's auto-fetch paginates 1,186 pages (5,000 parcels each, ~5.9M total). The previous fetch stalled at page 1,106 on a server-side HTTP 504 at deep offsets — intermittent server degradation, not a code bug. This 504 fragility is part of why the re-fetch is deferred rather than scheduled.

**If/when NC is picked up — to re-fetch:**
```bash
python -m app_puller   # use auto-fetch for nc_onemap_parcels
```
NC compose would run via the chunked path for the same memory reasons as FL.

NB: the puller's `prepare_fresh_partial()` wipes `.partial/` at start of every fetch → new fetch cannot resume from prior partial. Real resumability fix rides along with the deferred NC re-fetch.

### 4.3 Remaining stale on-disk items

- `composite/18` and `normalized/in_parcels` — IN dropped from this cut (ADR-017); safe to delete.

---

## 5. Commit state

Section 5 + the Section 4 source rewrites + AR/MT data-quality remediation + doc updates committed once the **AR + MT audit was clean** (revised gate; the prior gate "after FL composes" was moot while FL waited on chunked compose). `data/` is git-ignored — never commit raw or composite data.

This pivot's docs (this STATUS, SCOPE, GOALS, ROADMAP rewrites + 7 new ADRs + session summary + CONTEXT additions) commit as a single set documenting the 2026-05-25 phase shift.

**2026-05-29:** the audit-remediation work (map app fixes, preprocess hardening, FL recompose, doc reconciliation, CI lint/test fixes) was merged to `main` (PR #41; the stacked refactor + cleanup branches consolidated and deleted). The issue tracker was reconciled against this: **#9** (chunked compose), **#20** (FL compose), and **#14** (solar→parcel join) closed as completed; **#10**/**#21** (NC) marked `deferred`; **#27** (Steel-in-the-Air) flagged premise-overturned → `ready-for-human`.

---

## 6. Phase 1 slice progress

| Slice | State |
|---|---|
| **F** — Anchor composes (AR + MT + FL; FL recomposed 2026-05-29, county-score gap closed). NC compose deferred. | 🟢 Committed anchors composed — gate met; merged to `main` 2026-05-29 (closed #9 chunked compose, #20 FL compose) |
| **A** — FCC ULS carrier identification | ⬜ Next up |
| **C** — Asset enrichment + tunable scoring UI | ⬜ Partial: solar→parcel join done (#14); billboards partial (#13), scoring component-storage partial (#15), tunable UI not started (#29) |
| **D + E** — Lease docs + triage state + backend | ⬜ |
| **B** — Vendor inference | ⬜ |

Outcome bar: co-founder uses the product as his primary daily triage tool for 4 consecutive weeks (after Slice B ships). See [GOALS.md §3](./GOALS.md).

---

## 7. Outstanding decisions for the user

| Item | Notes |
|---|---|
| Chunked compose | ✅ Shipped 2026-05-19 (ADR-051). Single-shot retired 2026-05-27. |
| Steel-in-the-Air free dataset — **premise overturned 2026-05-26** | The free county-level lease-rate dataset doesn't exist (per data-source research, `docs/research/reports-2026-05-26/INDEX.md`). Slice D `lease_comp` source-of-truth needs replacement — next-best free path is REIT 10-K rent disclosures + ABS securitization filings. Paid Steel-in-the-Air tier remains the Phase 2 unlock per [ADR-057](./adr/0057-budget-posture-reframed.md). |
| libpostal vs `usaddress` for owner-clustering address normalization | Slice 4 implementation detail. Lean libpostal; fall back to `usaddress` if dep-management is painful. |
| Hosting choice (Fly.io vs Render vs Hetzner) | Slice 4 implementation detail; any small VM works per [ADR-055](./adr/0055-hosted-private-backend.md). |
| First Slice F PR | FL recompose **done** 2026-05-29 — county-score gap closed (§4.1); committed-anchor composes complete. The remediation (FL recompose + pipeline/app/doc fixes) is **uncommitted on disk** — the open call is whether to commit it as the first Slice F PR and formally open Slice A. NC re-fetch + compose stays deferred (§4.2). |
