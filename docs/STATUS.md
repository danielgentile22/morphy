# STATUS — Where the project stands today

**Last updated:** 2026-05-19
**Updated by:** automated audit at start of production-readiness push
**Updated when:** at the start of every section in the work plan, plus
weekly during execution.

This document is a **snapshot of reality**. If something here disagrees
with the code or data, the code/data wins and this doc is wrong (file a
fix). Aspirational state lives in [ROADMAP.md](./ROADMAP.md); the
working plan lives in `/.claude/plans/cached-wobbling-token.md`.

---

## 1. Anchor states

| State | Raw data | Normalized | Composed | Views | Notes |
|---|---|---|---|---|---|
| **AR** (05) | ✅ on disk | ✅ 2,116,976 parcels, owners populated | ✅ 9/9 joins, 0 warnings | **8** | Working end-to-end |
| **NC** (37) | ⚠ stale (2025-07-15, 11 months old); endpoint now responding again | — | — | — | User pulls fresh via puller in Section 4.4 |
| **MT** (30) | ❌ not yet pulled | — | — | — | MANUAL_ONLY; user pulls via puller walkthrough in Section 4.4 |
| **UT** (49) | ❌ not yet pulled | — | — | — | MANUAL_ONLY; user pulls in Section 4.4 |
| **FL** (12) | ❌ FGDL DSL deferred; FDOR NAL source added but no counties downloaded yet | — | — | — | User pulls 10 v1 counties via `fdor_nal` walkthrough in Section 4.4 |

States that are **dropped from this cut** but still have data on disk:

| State | Status | Reason |
|---|---|---|
| IN (18) | Composed; 3.7M parcels with no `owner_name` column | Indiana publishes no owner data. Deferred until paid source. |
| MN (27) | Not pulled | License "No License Provided" despite Open branding; deferred pending MnGeo confirmation |

---

## 2. Data sources

### Working

| Source | Last fetched | Cadence | Status |
|---|---|---|---|
| `fcc_asr` | 2026-05-18 | Weekly | ✅ |
| `faa_oeaaa` | 2026-05-15 | Daily | ✅ |
| `eia_860` | 2024 (annual) | Annual | ✅ post-openpyxl install |
| `eia_860m` | 2026-03 | Monthly | ✅ post-openpyxl install |
| `arc_distressed` | FY2026 | Annual | ✅ post-openpyxl install |
| `uspvdb` | 2026-04-14 | Quarterly | ✅ |
| `ar_parcels` | manual (current) | Annual | ✅ |
| `regrid_parcels` | — | — | Stub only (paid; out of scope) |

### Previously-broken endpoints (Section 4.1 — RESOLVED)

The 2025-cycle source-code fixes already landed in `scripts/fetch/sources/`
(URL updates baked in). As of 2026-05-19 all four endpoints respond on
`remote_version()`:

| Source | Last probe | Status |
|---|---|---|
| `hud_oz` | 2026-05-19 | ✅ returns 2026-02-24 |
| `hud_qct` | 2026-05-19 | ✅ returns 2025-09-22 |
| `usda_persistent_poverty` | 2026-05-19 | ✅ returns content-length fallback |
| `nc_onemap_parcels` | 2026-05-19 | ✅ returns layer-name fallback |
| `hifld_towers` | n/a | ⊘ RETIRED — moved to `_DEFERRED` (DHS removed layer in 2024) |

### Deferred sources (ADR-045)

Moved to `_DEFERRED` in `scripts/fetch/registry.py` — imported, but
hidden from the puller and preprocess. Reactivate by moving one line:

`hifld_towers`, `fcc_uls_*` (6 bands), `fcc_uls_meta`, `lbnl_tts`,
`fdot_billboards`, `ncdot_billboards`, `txdot_billboards`,
`fl_fgdl_parcels`, `in_parcels`, `mn_parcels`, `regrid_parcels`
(15 total).

### New for v1: `fdor_nal` (ADR-046)

Florida Department of Revenue per-county tax roll, MANUAL_ONLY with a
walkthrough listing 10 representative counties. Replaces the deferred
`fl_fgdl_parcels` (state-domain land, no owner data).

---

## 3. Code state

| Surface | State |
|---|---|
| `scripts/fetch/` | Headless puller library; 5 broken sources to fix in Section 4 |
| `scripts/preprocess/` | v3 framework running (Normalizer/Join/View registries, per-state Composer) |
| `scripts/preprocess/normalizers/` | 11 working + 16 source IDs with no normalizer |
| `scripts/preprocess/joins/` | 12 joins; 3 `county_score_to_*` recently patched for placeholder-column collision |
| `scripts/preprocess/views/` | 8 views |
| `app_puller/` | Qt desktop puller; functional but UX needs the Section 3 overhaul |
| `app/` | v1 Leaflet map with v3 catalog-discovery patches; cannot load huge parcel GeoJSONs (3.6 GB AR, 5.6 GB IN); title still hard-codes Graham County |
| `scripts/_legacy/preprocess_v1.py` | Dead code; archive + delete in Section 5.6 |

### Known performance hotspots

- `scripts/preprocess/normalizers/state_parcels.py:316` — `iterrows()`
  over 2–4M parcel rows; ~10 min per large state. Vectorize in Section 5.2.

### Manifest sync

- `data/manifest.json` (fetch manifest) — current per puller's last
  sweep.
- `data/processed/preprocess_manifest.json` — **stale**. Shows old
  failures already fixed (openpyxl) and AR with 1 view when it actually
  has 8. Resolved by `--rebuild-manifest` in Section 4.5.

---

## 4. Tests + CI

| Surface | State |
|---|---|
| Unit tests | **None** (Section 6) |
| Integration tests | **None** (Section 6) |
| E2E tests | **None** (Section 6) |
| CI | ✅ `lint.yml` (ruff) live on every push; `test.yml` is a placeholder until Section 6 |
| Schema validation | Not enforced yet (Section 6) |

---

## 5. Version control

| Surface | State |
|---|---|
| `git init` | ✅ Done 2026-05-19 |
| GitHub repo | ✅ `danielgentile22/infra-lease-analytics` (private) |
| `.gitignore` + `.gitattributes` | ✅ In place |
| CI workflows | ✅ `lint.yml` (ruff) + `test.yml` (placeholder until Section 6) |
| PR template + CODEOWNERS | ✅ In place |
| Branch protection | Deferred — adds full enforcement once tests land in Section 6 |

---

## 6. Documentation

| Surface | State |
|---|---|
| Root .md files | **3** files (README, CLAUDE, PROJECT_BRIEF); reorg complete 2026-05-19 |
| `docs/` directory | 15 docs + `archive/` + `pitch-assets/`; created 2026-05-19 |
| Stale references | Resolved 2026-05-19: PREPROCESSING_PLAN.md split → ARCHITECTURE.md + archive; CLAUDE.md slimmed; LIMITATIONS.md expanded; MAP_APP_REHAUL.md has DEFERRED header |
| New docs written | SCOPE, GOALS, STATUS, ROADMAP, DECISIONS, GLOSSARY, ARCHITECTURE, DATA_FRESHNESS, LIMITATIONS, TESTING, DEPLOYMENT, SECURITY, PULLER_UX, CHANGELOG, MAP_APP_REHAUL (moved + status-stamped) |

---

## 7. Outstanding blockers

| Blocker | Owner | Notes |
|---|---|---|
| GitHub repo visibility (private vs public) | User | Recommend private given PII (parcel-owner names + addresses) |
| FL FDOR NAL coverage list (which counties) | User | Recommend 5–10 representative: Miami-Dade, Hillsborough, Orange, Duval, Pinellas, Lee, Polk, Brevard, Volusia, Marion |
| Pitch-deck visual style (existing template / brand?) | User | Affects screenshot framing in Section 7.2 |

---

## 8. Most recent change

**2026-05-19** — Section 2 complete. GitHub repo
`danielgentile22/infra-lease-analytics` is live (private). CI
workflows green on first push. Ruff baseline applied across the
codebase (62 files reformatted, 281 lint auto-fixes). Now starting
Section 3 (data puller overhaul).
