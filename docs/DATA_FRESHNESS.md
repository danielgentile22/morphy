# Data freshness: per-source cadence rules

**Pairs with:** [DATA_SOURCES.md](./DATA_SOURCES.md) (per-source schema, license, and status), [PULLER_UX.md](./PULLER_UX.md) (puller UX), and section 8 below (Phase 1 product freshness UX).

This document sets out, per source, the rules the puller uses to decide
whether data is **fresh**, **due soon**, or **stale**. They map directly
onto the `update_cadence_days` field on each `DataSource` subclass and the
`next_recommended_check_at` field on the manifest (both implemented in
`scripts/fetch/manifest.py`).

---

## 1. How the cadence model works

Each source declares an `update_cadence_days: int | None`:

- **Integer N**: the publisher updates roughly every N days, so the local
  copy is stale once `today - fetched_at > N`.
- **`None`**: one-shot reference data (boundary files, historical
  designations). It never goes stale on its own. A `version_pin` field
  can override this.

At fetch time the puller computes `next_recommended_check_at = fetched_at + cadence_days`
for each source. The UI shows three states:

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
| `fcc_asr` | Weekly bulk export | **7** | The FCC publishes the Antenna Structure Registration (ASR) weekly databases every Sunday |
| `faa_oeaaa` | Daily | **1** | The FAA's Daily Obstruction File (DOF) updates nightly |
| `arc_distressed` | Annual (fiscal year) | **365** | The Appalachian Regional Commission (ARC) publishes a new fiscal-year list each October |
| `eia_860` | Annual | **365** | EIA publishes Form 860 once a year (usually fall) |
| `eia_860m` | Monthly | **30** | Form 860M is the monthly update |
| `uspvdb` | Quarterly | **90** | USGS / Berkeley refresh quarterly |
| `hud_oz` | Effectively static (OZ 1.0) | **None** | Opportunity Zone (OZ) 1.0 designations are frozen through 2028. The OZ 2.0 rollout in 2026-2028 needs a one-time refresh per redesignation event |
| `hud_qct` | Annual | **365** | HUD republishes Qualified Census Tract (QCT) designations annually |
| `usda_persistent_poverty` | ~5-10 years | **None** | Tied to Census decennial poverty data; reissues are rare and announced |
| `ar_parcels` | Annual (state aggregates from county computer-assisted mass appraisal (CAMA) systems) | **365** | The Arkansas Geographic Information Office typically refreshes the statewide layer annually |
| `mt_cadastral_parcels` | Quarterly | **90** | MT Cadastral publishes a refresh quarterly |
| `wv_parcels` | Annual | **365** | The WV Property Tax Division and the WVU GIS Technical Center (MapWV) refresh the statewide layer annually (committed anchor, ADR-060) |
| `nc_onemap_parcels` | Per county, varies (monthly to quarterly) | **90** | NC OneMap mirrors county exports; a quarterly refresh balances load |
| `fdor_nal` | Annual (county-by-county certification each October) | **365** | The FL Department of Revenue (DOR) finalizes tax-roll certification by October; per-county downloads follow shortly after |

---

## 3. Deferred and retired sources

Deferred and retired sources appear in the puller for visibility but get no freshness alerts. The canonical status list lives in the status notes in [DATA_SOURCES.md](./DATA_SOURCES.md), with the ADR behind each one.

Deferred parcel sources keep a nominal `update_cadence_days` so they can be re-promoted by editing the active block alone. For example, `ut_parcels` (cadence **365**) is deferred from the anchor set because it has no owner data (ADR-049), and `mn_parcels` / `in_parcels` are likewise in `DEFERRED_SOURCES`.

---

## 4. What "stale" means in practice

When the puller marks a source **Stale**, the developer should refresh
it **before** re-running preprocess ahead of a serious triage session.
In detail:

- For **`fcc_asr`** and **`faa_oeaaa`**, stale means noise. A week-old ASR
  is fine for general analysis; refresh before serious triage.
- For **parcel sources** (annual cadence), stale data leads to false
  positives: owners may have sold, and addresses change. Refresh quarterly
  when the data is used to contact owners, and at least annually otherwise.
- For **distress overlays** (OZ, QCT, ARC, and the USDA persistent-poverty
  list), staleness is rare and comes from external events (an annual
  republish, the OZ 2.0 designation cycle). News, not the calendar,
  should prompt a manual refresh.
- For **EIA 860/860M**, the monthly data informs trends; the annual file is
  the canonical plant inventory.

---

## 5. Refresh checklist before serious triage

Before a serious triage session, the developer ran this refresh pass in the puller:

1. Click **Check for updates**. It lists every source past `next_recommended_check_at`.
2. Refresh stale sources (automated sources through the puller; manual sources through the walkthrough).
3. Re-run preprocess on the affected states.
4. Check that [STATUS.md](./STATUS.md) matches reality.

[PULLER_UX.md](./PULLER_UX.md) describes this checklist as a UI flow, along with the standing "What needs my attention" panel that gathers stale and missing sources.

---

## 6. Source changes that *don't* trip cadence alerts

Some real-world events change data without moving the cadence clock.
Trigger a refresh by hand after:

- **HUD OZ 2.0 redesignations** announced during 2026-2028. Until that
  rollout completes, treat OZ as frozen.
- **Major regulatory change**, such as the FCC restructuring ASR endpoints.
  These usually break `fetch()` rather than affect staleness.
- **An off-cycle state update**, for example NC OneMap pushing a
  schema-correcting refresh mid-year.
- **A question about recent change**, such as the user asking "what changed
  in X county between Q1 and Q2?" Force a refresh before answering.

The puller's UI cannot detect these. Note any off-cadence refresh in the relevant commit message; git log is the canonical history.

---

## 7. Implementation hooks

The cadence model in this document is fully implemented. This section maps
where it lives:

- `update_cadence_days` on each `DataSource`, the manifest
  `next_recommended_check_at` / `recompute` logic, and the
  `FRESHNESS_FRESH` / `DUE_SOON` / `STALE` states live in
  `scripts/fetch/manifest.py`.
- The freshness column and the "What needs my attention" panel (stale and
  missing sources) are in the puller UI (see [PULLER_UX.md](./PULLER_UX.md)).
  The original Qt desktop puller was later deleted, and the data TUI is the
  only puller UI.
- Every active source sets `update_cadence_days` per the table above.

---

## 8. Phase 1 product UX for freshness (Slice C and Slice D+E)

The puller shows freshness to the developer, who operates it. The Phase 1 product was designed to show freshness to the user, so they could judge how far to trust a specific lead.

### Surfaces

| Surface | What's shown | Where it lands |
|---|---|---|
| Top of triage list | "Last full data refresh: AR 12d, MT 9d, FL 47d, WV 21d" | Slice C UI (map app) |
| Per-lead detail panel | "Parcel data from {date}; tower data from {date}; lease comp data from {date}" | Slice C / D+E lead-detail panel |
| Per-source admin view (gated) | Per-source freshness table plus a refresh-trigger button | D+E backend admin. This admin view was never built, and the refresh trigger was Phase 2 |

### Staleness policy

- **Information only for most sources.** Show the age, let the user judge, and **don't block triage**.
- **One hard banner** when a state's parcel source is **> 180 days old**: *"AR parcels last refreshed 192 days ago. Schedule a re-pull before working AR leads."* It warns prominently but still doesn't block.
- **Carrier (FCC Universal Licensing System) staleness** gets a soft warning only. Carriers don't leave towers quickly.
- **Distress overlays** get a soft warning. OZ and ARC tiers update annually.

### Refresh trigger model

- **Phase 1: developer-only refresh.** The developer ran the puller; the user saw freshness state but did not trigger refreshes. This was simpler, because the puller is a local tool and not easily driven from the backend.
- **Phase 2: self-serve refresh from the product** was planned but never built. It would have wired the puller into the backend so the user could press a button.

### The MANUAL_ONLY cost

Sources flagged MANUAL_ONLY need someone to walk through them at every refresh. The worst was FDOR NAL before it was automated on 2026-07-03: 67 Florida counties, each needing its own selection and click-through. Phase 1 did not otherwise address this. The Phase 2 options were a guided checklist UI in the puller or paid bulk-data unlocks (consistent with ADR-057's reframing of ADR-010).
