# Audit: ULS `asr_number` coverage + ULS↔ASR join tolerance calibration

**Issue:** [#11](https://github.com/danielgentile22/infra-lease-analytics/issues/11) ·
**Feeds:** [#24](https://github.com/danielgentile22/infra-lease-analytics/issues/24) (the hybrid join) ·
**Date:** 2026-05-30 · **Status:** calibration spike (analysis only — no pipeline changes)

## Headline

| Question | Answer |
|---|---|
| What share of in-scope ULS `LO` records carry a populated `asr_number`? | **55.7% overall** — **59.1% Cellular**, **0% PCS/AWS/700** |
| Recommended proximity tolerance → confidence tiers for #24 | exact `asr_number` → **`verified`** · nearest ASR tower **≤ 100 m → `likely`** · **≤ 500 m → `possible`** · **> 500 m → no match** |

These confirm #24's placeholder defaults (100 m `likely` / 500 m `possible`) are
well-calibrated, now backed by the measured drift distribution rather than a guess.

---

## 1. `asr_number` coverage

In-scope = Cellular (Part 22, `fcc_uls_cellular`) + the PCS/AWS/700 service-code
subset of the market bundle (`fcc_uls_market`). WCS/Microwave deferred.

| band | `LO` rows | `asr_number` populated | coords present |
|---|---:|---:|---:|
| cellular | 25,046 | **14,801 (59.1%)** | 25,046 (100.0%) |
| pcs | 1,164 | 0 (0.0%) | 1,164 (100.0%) |
| aws | 7 | 0 (0.0%) | 7 (100.0%) |
| 700mhz | 369 | 0 (0.0%) | 369 (100.0%) |
| **all in-scope** | **26,586** | **14,801 (55.7%)** | **100.0%** |

**Read:** `asr_number` coverage is **bimodal, not uniform**. Cellular is
site-based (Part 22), so ~59% of its `LO` records name the registered ASR tower
they sit on — a high-precision exact key. PCS/AWS/700 are **market/geographic-area**
licenses (Part 24/27): their handful of `LO` records describe the licensed area,
not a registered structure, so **none** carry an `asr_number`. (Sanity check
against raw `l_market/LO.dat`: only 294 of 19,104 rows across *all* market services
carry one, and every one of those falls in an out-of-scope service — none in the
PCS/AWS/700 subset.) Because Cellular supplies all 14,801 tagged rows and the other
three bands supply zero, the cross-reference path is effectively a Cellular feature;
for PCS/AWS/700 **every** carrier match in #24 must come from the spatial fallback.

**Coordinate reliability:** the well-known "ULS coordinates are blank/zero" caveat
**does not hold for these site-based bands** — raw `LO` lat/lon is populated on
100.0% of Cellular rows and 99.99% of market rows (2 blanks in 19,104). The problem
is **drift, not blankness** — quantified next.

---

## 2. Tolerance calibration — ULS-coord → ASR-tower-coord drift

**Method.** The `asr_number`-tagged records are a *labeled* set: each pins a
(ULS `LO` coordinate, ASR tower coordinate) pair for the **same physical structure**
(join `uls.asr_number = asr.registration_number`; the ASR key is unique — clean 1:1,
no dedup). The great-circle distance between the two coordinates is exactly how far
a ULS coordinate drifts from the true tower location — the empirical basis for how
close a *non*-tagged ULS record's coordinate must be to an ASR tower before #24 can
believe they are the same structure.

- Tagged `LO` rows (asr_number + valid coords): **14,801**
- Matched to an ASR tower: **14,794 (100.0%)** — 7 unmatched (stale registration ids)
- All pairs from Cellular (PCS/AWS/700 contribute none — see §1)
- **Anchor-state pairs (AR/MT/FL/WV): 1,488** ← primary calibration set

### Drift distribution

| percentile | **Anchor (n=1,488)** | National (n=14,794) |
|---|---:|---:|
| p50 | **0 m** | 0 m |
| p75 | **3 m** | 4 m |
| p90 | **22 m** | 33 m |
| p95 | **44 m** | 64 m |
| p99 | **265 m** | 235 m |
| mean | 34 m | 167 m |
| max | 34,205 m | 1,475,696 m |

| cutoff | **Anchor ≤** | National ≤ |
|---|---:|---:|
| ≤ 50 m | **95.5%** | 93.4% |
| ≤ 100 m | **97.8%** | 97.2% |
| ≤ 250 m | **98.9%** | 99.1% |
| ≤ 500 m | **99.9%** | 99.6% |
| ≤ 1000 m | 99.9% | 99.8% |

**Read:** the distribution is **very tight**. Half of all ULS coordinates land
*exactly* on the tower (0 m — both sides derive from the same DMS registration for
that structure); 90% are within ~22–33 m; 95% within ~44–64 m. A genuine
co-located pair is within **100 m 97–98%** of the time and within **500 m 99.6–99.9%**
of the time. Anchor and national agree closely, so the small anchor sample is
trustworthy. The far tail (national max 1.5M km-scale, i.e. a sign-flipped /
mistyped coordinate) is **data-entry garbage** — a few records that are *not* where
they claim. This tail is itself an argument for a hard distance cap: those are
exactly the records #24 must **refuse** to match spatially.

---

## 3. Recommended tolerance bands → confidence tiers (for #24)

| tier | rule | rationale |
|---|---|---|
| **`verified`** | `uls.asr_number = asr.registration_number` (exact) | Cross-reference, no distance needed. Available on 55.7% of in-scope rows (59.1% Cellular; 0% PCS/AWS/700). 100% of tagged rows match a real tower. |
| **`likely`** | nearest ASR tower **≤ 100 m** | p95 of true co-located drift is 44 m (anchor) / 64 m (national); 100 m covers **97–98%** of genuine same-structure pairs while staying tight enough to avoid grabbing a *neighbouring* tower. Roughly the p97 of real drift. |
| **`possible`** | nearest ASR tower **> 100 m and ≤ 500 m** | Captures the real-but-drifted tail up to **99.6–99.9%** of genuine pairs. The 100–500 m band mixes true drift with the onset of ambiguity, so tag it lower-confidence. |
| *(no match)* | nearest ASR tower **> 500 m** | Beyond 500 m only 0.1–0.4% of genuine pairs remain — not worth the false-positive risk, and this is where the data-entry-error tail lives. |

**Why 100/500 and not 50 m?** Issue #11's heuristic: if `asr_number` coverage
≥ 50%, a generous fallback is fine; if < 30%, tighten to 50 m for precision. At
**55.7% overall (59.1% Cellular)** the cross-reference dominates, so the generous
fallback applies. More importantly the **drift distribution directly supports it**:
50 m would only reach p93–95 and needlessly drop ~3–4% of genuine pairs that sit at
50–100 m, whereas 100 m reaches ~p97 with little added ambiguity. The anchor states
(AR/MT/WV especially) are **rural with sparse towers**, so a 100 m `likely` / 500 m
`possible` radius is safe there — the nearest ASR tower to a real ULS site is almost
never a *different* tower within 500 m.

**Consequence for #24's ≥70% coverage gate:** because PCS/AWS/700 carry no
`asr_number`, their carrier identification rests entirely on the spatial fallback;
Cellular (59% verified + ~41% spatial) will carry the gate. The tight drift
distribution means the spatial fallback is reliable, so the gate is reachable.

---

## 4. Reproduce

```bash
source .venv/bin/activate
python scripts/audits/uls_asr_number_coverage.py
```

Reads (no raw parsing, no recompute):
- `data/processed/normalized/fcc_uls_cellular/location.parquet` and
  `data/processed/normalized/fcc_uls_market/{pcs,aws,700mhz}/location.parquet` — the
  #12 normalizer output (`asr_number` + DMS→decimal EPSG:4326 coords already parsed).
- `data/processed/normalized/fcc_asr/towers.parquet` — ground-truth tower set
  (`asr_number`, `lat`, `lon`, `state_fips`).

The script is a **throwaway one-off** under `scripts/audits/` — not part of the
preprocess pipeline. Its vectorised haversine helper runs a built-in self-test
(known city distances + 1°-latitude check) on every invocation.

## 5. Limitations

- **Calibration is Cellular-only.** Only Cellular carries `asr_number`, so the
  drift distribution reflects Cellular `LO` coordinates. PCS/AWS/700 coordinate
  quality is unmeasured here (no labeled pairs); applying the same tolerance to
  them is an assumption #24 inherits — reasonable, since all bands share the same
  ULS DMS coordinate pipeline, but unverified.
- **National vs anchor.** ASR towers are normalized nationally, so calibration was
  run on the anchor subset (primary) *and* nationally (stability check); they agree.
  Recommendations are anchored to AR/MT/FL/WV — the Phase-1 towers that matter.
- **Small anchor sample** (1,488 pairs) — but the percentiles track the 14,794-pair
  national set closely, so they are not artefacts of sample size.
- **Drift ≠ accuracy.** A 0 m drift means ULS and ASR agree, not that *either* is
  truly correct — both inherit the same registrant-supplied DMS coordinate. The
  audit measures agreement between the two sources for the same structure, which is
  the right quantity for setting a *matching* tolerance.
- Snapshot of the ULS/ASR bulk extracts on disk (fetched 2026-05-17); coverage and
  drift will shift slightly on refresh but the distribution shape is stable.
