# DATA_FRESHNESS — Per-source cadence rules

**Last updated:** 2026-06-26
**Pairs with:** [DATA_SOURCES.md](./DATA_SOURCES.md) (per-source schema + license + status), [PULLER_UX.md](./PULLER_UX.md) (puller UX), [SCOPE.md §6](./SCOPE.md) (Phase 1 product freshness UX).

This document codifies, per source, the rules the puller uses to decide
whether data is **fresh**, **due soon**, or **stale**. These map
directly onto the `update_cadence_days` field on each `DataSource`
subclass and the `next_recommended_check_at` field on the manifest
(both implemented in `scripts/fetch/manifest.py`).

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
| `mt_cadastral_parcels` | Quarterly | **90** | MT Cadastral publishes a refresh quarterly |
| `wv_parcels` | Annual | **365** | WV Property Tax Division / WVU GIS Technical Center (MapWV) refresh the statewide layer annually (committed anchor — ADR-060) |
| `nc_onemap_parcels` | Per-county, varies (monthly–quarterly) | **90** | NC OneMap mirrors county exports; refresh quarterly to balance load |
| `fdor_nal` | Annual (county-by-county certification each October) | **365** | FL DOR finalizes tax-roll certification by October; per-county downloads available shortly after |

---

## 3. Deferred / retired sources

Deferred / retired sources appear in the puller for visibility but are not subject to freshness alerting. The canonical status list lives in [DATA_SOURCES.md §Status overrides](./DATA_SOURCES.md) (ADR-linked rationale per source).

Deferred parcel sources keep a nominal `update_cadence_days` so they can be re-promoted by editing the active block alone — e.g. `ut_parcels` (cadence **365**) is deferred from the anchor set (no owner data — ADR-049), and `mn_parcels` / `in_parcels` are likewise in `DEFERRED_SOURCES`.

---

## 4. What "stale" means in practice

When the puller marks a source **Stale**, the user should refresh
**before** they re-run preprocess for a material co-founder triage session.
Specifically:

- For **`fcc_asr`** and **`faa_oeaaa`**: stale = noise. A week-old ASR
  is fine for general analysis; refresh before serious triage.
- For **parcel sources** (annual cadence): stale data leads to false
  positives — owners may have sold, addresses changed. Refresh quarterly
  if doing real outreach; minimum annually.
- For **distress overlays** (OZ, QCT, ARC, USDA): stale is rare and
  signaled by external events (annual republish, OZ 2.0 designation
  cycle). Manual refresh prompts triggered by news, not calendar.
- For **EIA 860/860M**: monthly data informs trend narratives; annual is
  the canonical source of plant inventory.

---

## 5. Refresh discipline before serious triage

Before any material co-founder triage session, the user runs a refresh discipline pass in the puller:

1. Click **Check for updates** — surfaces every source past `next_recommended_check_at`.
2. Refresh stale sources (auto sources via puller; manual sources via walkthrough modal).
3. Re-run preprocess on affected states.
4. Verify [STATUS.md](./STATUS.md) matches reality (or update it).

This checklist is mirrored in [PULLER_UX.md](./PULLER_UX.md) §6 as a discrete UI flow; the standing "What needs my attention" panel that aggregates stale + missing sources is [PULLER_UX.md](./PULLER_UX.md) §3.

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

The puller's UI cannot detect these. Note any off-cadence refresh in the relevant commit message; git log is the canonical history.

---

## 7. Implementation hooks (shipped)

The cadence model in this document is fully implemented; the Qt puller is
now frozen (PRD #138), so this section is a map of where it lives rather
than a work plan:

- `update_cadence_days` on each `DataSource` + the manifest
  `next_recommended_check_at` / `recompute` logic and the
  `FRESHNESS_FRESH` / `DUE_SOON` / `STALE` states live in
  `scripts/fetch/manifest.py`.
- Freshness column + the "What needs my attention" panel (stale +
  missing) are in the puller tree (see [PULLER_UX.md](./PULLER_UX.md) §3).
- Every active source populates `update_cadence_days` per the table above.

---

## 8. Phase 1 product UX for freshness (Slice C + Slice D+E)

The puller surfaces freshness to the dev (the operator). The Phase 1 product surfaces freshness to the **co-founder** (the user) so he can judge confidence on a specific lead. See [SCOPE.md §6](./SCOPE.md) for the product-side policy.

### Surfaces

| Surface | What's shown | Where it lands |
|---|---|---|
| Top of triage list | "Last full data refresh: AR 12d, MT 9d, FL 47d, WV 21d" | Slice C UI (map app) |
| Per-lead detail panel | "Parcel data from {date}; tower data from {date}; lease comp data from {date}" | Slice C / D+E lead-detail panel |
| Per-source admin view (gated) | Per-source freshness table + refresh-trigger button | D+E backend admin (the write-layer backend is live in production; this admin surface is unbuilt); refresh-trigger is Phase 2 |

### Staleness policy

- **Information-only for most sources** — show the age, let the co-founder judge; **don't block triage**.
- **One hard banner** when a state's parcel source is **> 180 days old**: *"AR parcels last refreshed 192 days ago — schedule a re-pull before working AR leads."* Warns prominently; still doesn't block.
- **Carrier (ULS) staleness** — soft warning only. Carriers don't churn off towers fast.
- **Distress overlays** — soft warning. OZ annual; ARC tiers annual.

### Refresh trigger model

- **Phase 1 = dev-only refresh.** You run the puller; co-founder sees freshness state but does not trigger refreshes himself. Simpler; the puller is currently a Qt desktop app and not easily backend-driven.
- **Phase 2 = self-serve refresh from product.** Wire the puller into the backend so the co-founder presses a button. Real work — out of Phase 1 scope.

### MANUAL_ONLY pain (acknowledged)

Sources flagged MANUAL_ONLY (notably **FDOR NAL** — 67 Florida counties, each requiring per-county selection + click-through) need *you* to walk through them at every refresh. **Phase 1 does not fix this.** Phase 2 candidates: guided checklist UI in the puller, or paid bulk-data unlocks (consistent with ADR-057's reframing of ADR-010).
