# STATUS — Where the project stands today

**Last updated:** 2026-05-20
**Updated by:** data cleanup — FL processed data + NC raw and processed data deleted
**Update cadence:** at the start of every work-plan section and at every session handoff.

A snapshot of reality. If this disagrees with the code or data, the
code/data wins — fix the doc.

---

## 0. TL;DR

Mid-**Section 5** (preprocess code hygiene). Sections 1–4 done.
Section 5 code is written but **not committed** (last commit `a067a49`).

- **AR + MT** — compose cleanly end-to-end. Solid.
- **FL** — raw data intact (all 67 counties, ~28 GB). Normalized data
  and composite **deleted 2026-05-20** to free disk. Needs full
  re-normalize + compose before pitch. The chunked compose (ADR-051)
  must be built first — §4.1.
- **NC** — all raw data **deleted 2026-05-20** (nc_onemap_parcels +
  legacy NC/ directory). Was never normalized or composed. Needs a
  full re-fetch from NC OneMap, then normalize + compose — §4.2.

**Next steps, in order:** (1) build the chunked compose (ADR-051);
(2) re-normalize + compose FL; (3) re-fetch NC when the endpoint is
stable, then normalize + compose NC; (4) commit Section 5;
(5) Section 6 (testing).

---

## 1. Anchor states

| State | Raw data | Normalized | Composed | Notes |
|---|---|---|---|---|
| **AR** (05) | ✅ | ✅ 2,116,976 parcels | ✅ 9 joins, 8 views, 0 warnings | Works end-to-end. |
| **MT** (30) | ✅ all 56 counties | ✅ 920,111 parcels, 96% owner names | ✅ 9 joins, 8 views, 0 warnings | Works end-to-end. |
| **FL** (12) | ✅ all 67 counties (~28 GB raw intact) | ❌ deleted 2026-05-20 | ❌ | Needs re-normalize + compose; chunked compose required first (§4.1). |
| **NC** (37) | ❌ deleted 2026-05-20 | ❌ | ❌ | All raw deleted; needs full re-fetch from NC OneMap (§4.2). |

Dropped from this cut: IN (18) and UT (49) — no owner data; MN (27) —
license ambiguity.

---

## 2. What works

- **AR + MT end-to-end** — pull → normalize → compose → 8 views.
- The v3 preprocess framework, the puller (Section 3), Git + CI.
- **FL normalizer code** is correct and verified (geometry bug fixed;
  ADR-050 streaming per-county normalizer). The normalized output was
  deleted for disk space; re-running `python scripts/preprocess.py
  --state 12` will re-produce it once disk space is available and the
  chunked compose is in place.

---

## 3. What does NOT work / is incomplete

| Item | Severity | Detail |
|---|---|---|
| FL normalized data | 🚫 Deleted | Deleted 2026-05-20 to free disk. Re-run normalizer when chunked compose is ready. |
| FL compose | 🚫 Blocked | Needs chunked compose (ADR-051) first, then re-normalize, then compose. §4.1 |
| NC raw data | 🚫 Deleted | Deleted 2026-05-20. Needs full re-fetch from NC OneMap when endpoint is stable. §4.2 |
| NC normalize + compose | 🚫 Blocked | Gated on NC re-fetch; will also need chunked compose. |
| Chunked compose | ⬜ To build | Approved (ADR-051); not started. Required for both FL and NC. |
| Section 5 commit | ⏳ Pending | ~33 files modified, uncommitted. §5 |
| `composite/18`, `normalized/in_parcels` | ℹ️ Note | Still on disk; safe to delete (IN dropped from this cut). |
| `preprocess_manifest.json` | ℹ️ Rebuilt | Rebuilt 2026-05-20 via `--rebuild-manifest`; shows 9 normalized sources + 3 composed states (AR/IN/MT). |
| Tests | ⬜ Not started | Section 6. |

---

## 4. Known issues — detail

### 4.1 FL — normalized data deleted; chunked compose needed

FL's normalized output (~10.2 GB, 68 county parquet files, 11,184,113
parcels) was deleted 2026-05-20 to recover disk space. The raw FDOR
NAL data is untouched at `data/raw/fdor_nal/current/` (~28 GB, all 67
counties).

Re-normalizing is straightforward — the normalizer code is correct and
verified. The blocker is composing: FL's 11.18M parcels require
**~19.5 GB peak RAM** and **~16–20 GB disk** for the composite output,
which exceeds the 16 GB dev machine. The fix is the **chunked compose**
(ADR-051): stream parcels county-by-county so peak memory stays bounded.

**To re-run FL end-to-end once chunked compose is built:**
```bash
python scripts/preprocess.py --state 12
```

### 4.2 NC — all raw data deleted; needs full re-fetch

Both `data/raw/nc_onemap_parcels/` (~8.3 GB, 1,106 of 1,186 MapServer
pages) and `data/raw/NC/` (~958 MB, Graham County shapefiles + legacy
FCC docs) were deleted 2026-05-20.

NC OneMap's auto-fetch paginates 1,186 pages (5,000 parcels each,
~5.9M total). The previous fetch stalled at page 1,106 on a server-side
HTTP 504 at deep offsets — an intermittent server degradation, not a
code bug. Re-fetch when the endpoint is confirmed stable.

**To re-fetch NC:**
```bash
python -m app_puller   # use auto-fetch for nc_onemap_parcels
```
NC compose will also need the chunked compose (ADR-051) for the same
memory reasons as FL.

NB: the puller's `prepare_fresh_partial()` wipes `.partial/` at the
start of every fetch, which means the new fetch cannot resume from the
prior partial. A real resumability fix is a known follow-up.

### 4.3 Disk freed by cleanup

The 2026-05-20 cleanup deleted ~20.9 GB:
- `data/raw/nc_onemap_parcels/` — 8.3 GB
- `data/raw/NC/` — 0.9 GB
- `data/processed/normalized/fdor_nal/` — 10.2 GB
- `data/processed/composite/12/` — 70 MB
- `data/_stale_backup/` — 2.3 GB

FL raw at `data/raw/fdor_nal/current/` is untouched (~28 GB).

### 4.4 Remaining stale on-disk items

- **`composite/18` and `normalized/in_parcels`** — still on disk; safe
  to delete (IN dropped from this cut — ADR-017).

---

## 5. Uncommitted work

All of Section 5 + the Section 4 source rewrites + doc updates are
uncommitted (~33 files; last commit `a067a49`). Commit after FL
composes cleanly so the commit captures a verified-working state.
`data/` is git-ignored — never commit raw or composite data.

---

## 6. Work-plan progress

| Section | State |
|---|---|
| 1 — Documentation foundation | ✅ Complete |
| 2 — Version control + GitHub | ✅ Complete |
| 3 — Data puller overhaul | ✅ Complete |
| 4 — Data hygiene / raw refresh | ⚠️ AR/MT pulled and solid; FL raw intact, processed deleted; NC all data deleted |
| 5 — Preprocess code hygiene | ⚠️ Code written + uncommitted; AR/MT verified; FL/NC need chunked compose before re-running |
| 6 — Testing | ⬜ Not started |
| 7 — Pitch readiness | ⬜ Not started |
| 8 — Map app (minimal patches) | ⬜ Not started |

NB: CLAUDE.md and this doc reference a work-plan file at
`.claude/plans/cached-wobbling-token.md` — that file is **not on disk**.
The section table above is the authoritative tracker until it is
restored.

---

## 7. Outstanding decisions for the user

| Item | Notes |
|---|---|
| Chunked compose | Approved (ADR-051); implementation not started. Required before FL re-normalize + compose and NC compose. |
| Pitch-deck visual style | Still open (affects Section 7 screenshot framing). |
