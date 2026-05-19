# DATA_FRESHNESS — Per-source cadence rules

**Last updated:** 2026-05-19
**Pairs with:** [DATA_SOURCES.md](./DATA_SOURCES.md) (per-source schema
+ license) and [PULLER_UX.md](./PULLER_UX.md) (UX design for surfacing
this in the puller).

This document codifies, per source, the rules the puller uses to decide
whether data is **fresh**, **due soon**, or **stale**. These map
directly onto the `update_cadence_days` field on each `DataSource`
subclass (added in Section 3.1 of the work plan) and the
`next_recommended_check_at` field on the manifest.

---

## 1. How the cadence model works

Each source declares an `update_cadence_days: int | None`:

- **Integer N** — the publisher updates approximately every N days; we
  consider the local copy stale once `today - fetched_at > N`.
- **`None`** — one-shot reference data (boundary files, historical
  designations); never goes stale on its own. A `version_pin` field
  can override.

The puller computes a `next_recommended_check_at` per source at fetch
time = `fetched_at + cadence_days`. Three states surfaced in the UI:

| State | Definition | Visual cue |
|---|---|---|
| **Fresh** | `today < next_recommended_check_at - 0.5 × cadence` | Green badge |
| **Due soon** | `next_recommended_check_at - 0.5 × cadence ≤ today < next_recommended_check_at` | Yellow badge |
| **Stale** | `today ≥ next_recommended_check_at` | Red badge |

Sources with `update_cadence_days = None` show no badge but display
`fetched_at` in the details pane.

---

## 2. Cadence table (active sources)

| Source ID | Publisher cadence | `update_cadence_days` | Rationale |
|---|---|---|---|
| `fcc_asr` | Weekly bulk export | **7** | FCC publishes the ASR weekly databases every Sunday |
| `faa_oeaaa` | Daily | **1** | DOF (Daily Obstruction File) updates nightly |
| `arc_distressed` | Annual (FY) | **365** | ARC publishes a new fiscal-year list each October |
| `eia_860` | Annual | **365** | EIA publishes Form 860 once a year (usually fall) |
| `eia_860m` | Monthly | **30** | Form 860M is the monthly update |
| `uspvdb` | Quarterly | **90** | USGS / Berkeley refresh quarterly |
| `hud_oz` | Effectively static (OZ 1.0) | **None** | OZ 1.0 designations are frozen through 2028; OZ 2.0 rollout 2026–2028 will need a one-time refresh per redesignation event |
| `hud_qct` | Annual | **365** | HUD republishes QCT designations annually |
| `usda_persistent_poverty` | ~5–10 years | **None** | Tied to Census decennial poverty data; reissue is rare and announced |
| `ar_parcels` | Annual (state aggregates from county CAMA) | **365** | Arkansas Geographic Information Office typically refreshes statewide layer annually |
| `nc_onemap_parcels` | Per-county, varies (monthly–quarterly) | **90** | NC OneMap mirrors county exports; refresh quarterly to balance load |
| `mt_cadastral_parcels` | Quarterly | **90** | MT Cadastral publishes a refresh quarterly |
| `ut_parcels` | Annual | **365** | UT statewide parcel project refreshes annually |
| `fdor_nal` | Annual (county-by-county certification each October) | **365** | FL DOR finalizes tax-roll certification by October; per-county downloads available shortly after |

---

## 3. Deferred / retired sources (not surfaced as actionable)

These appear in the puller for visibility but are not subject to
freshness alerting:

| Source ID | State | Notes |
|---|---|---|
| `hifld_towers` | **Retired** | DHS retired in 2024; no further updates expected |
| `regrid_parcels` | Out of scope (paid) | `update_cadence_days = None`; user opts in only if budget unlocks |
| `lbnl_tts` | Deferred | Dropped from active registry; cadence ignored |
| `fcc_uls_*` (6 bands) | Deferred | Cadence is weekly upstream; raw data refreshable manually if user wants, but no normalize path |
| `state_billboards` (FDOT, NCDOT, TXDOT) | Deferred | Cadence varies; not pursued |
| `fl_fgdl_parcels` | Replaced by `fdor_nal` | Hidden in registry |
| `in_parcels` | Dropped from anchors | No owner data |
| `mn_parcels` | Deferred (license) | Pending MnGeo confirmation |

---

## 4. What "stale" means in practice

When the puller marks a source **Stale**, the user should refresh
**before** they re-run preprocess for a pitch demo or partner walkthrough.
Specifically:

- For **`fcc_asr`** and **`faa_oeaaa`**: stale = noise. A week-old ASR
  is fine for general analysis; refresh before pitch.
- For **parcel sources** (annual cadence): stale data leads to false
  positives — owners may have sold, addresses changed. Refresh quarterly
  if doing real outreach; minimum annually before pitch.
- For **distress overlays** (OZ, QCT, ARC, USDA): stale is rare and
  signaled by external events (annual republish, OZ 2.0 designation
  cycle). Manual refresh prompts triggered by news, not calendar.
- For **EIA 860/860M**: monthly data informs trend narratives; annual is
  the canonical source of plant inventory.

---

## 5. Refresh discipline at pitch time

Before any pitch / partner walkthrough, the user runs a **pre-pitch
checklist** in the puller:

1. Click **Check for updates** — surfaces every source past
   `next_recommended_check_at`.
2. Refresh stale sources (auto sources via puller; manual sources via
   walkthrough modal).
3. Re-run preprocess on affected states.
4. Verify `docs/STATUS.md` matches reality (or update it).
5. Re-record `docs/NUMBERS.md` if any totals changed.

This checklist is mirrored in [PULLER_UX.md](./PULLER_UX.md) §6 as a
discrete UI flow (the "What needs my attention" panel).

---

## 6. Source-changes that *don't* trip cadence alerts

Some real-world events change data without bumping the cadence clock.
Manually trigger a refresh after:

- **HUD OZ 2.0 redesignations** announced during 2026–2028. Until that
  rollout completes, treat OZ as effectively frozen.
- **Major regulatory change** — FCC restructures ASR endpoints, etc.
  These usually break `fetch()`, not staleness.
- **State publishes off-cycle update** — e.g., NC OneMap pushes a
  schema-correcting refresh mid-year.
- **News-event-driven need** — a partner asks "what changed in
  X county between Q1 and Q2?" — force-refresh before answering.

The puller's UI cannot detect these. Document in CHANGELOG.md when a
manual off-cadence refresh happens.

---

## 7. Implementation hooks (for the Section 3 puller overhaul)

This document drives concrete code changes in Section 3 of the work plan:

- **3.1:** `update_cadence_days` field on `DataSource` + manifest
  schema-version bump.
- **3.3:** Freshness column in puller tree.
- **3.3:** "What needs my attention" panel aggregating stale + missing.
- **3.5:** Every active source populates `update_cadence_days` per
  this table.
