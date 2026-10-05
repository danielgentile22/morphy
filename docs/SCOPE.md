# SCOPE — Phase 1 Product (what we're building + why + what success is)

**Last updated:** 2026-06-26
**Status:** Active — Phase 1 in progress (most slices shipped; product live in production)

This is the **single source of truth for what we are building, why, and what "done"
looks like.** It owns the **canonical anchor-state list (§2)** and the **canonical slice
plan (§3)** — STATUS, ROADMAP, and CLAUDE reference these rather than restating them.
Anything not listed here is out of scope for Phase 1.

For the strategic pivot from pitch demo → product, see
[ADR-053](./adr/0053-product-phase-shift.md). Today's exact state is in
[STATUS.md](./STATUS.md); the future is in [ROADMAP.md](./ROADMAP.md).

---

## 1. What Phase 1 is, and why

**North star:** a business that moves real economic value to the **landowner** side of
infrastructure ground-leases — primarily cell towers — by using public + private data to
identify, prioritize, and equip landowners to renegotiate undervalued contracts or evaluate
unsolicited buyout offers. The product in this repo is the **co-founder's working tool** to
do that triage; it's the foundation layer of the broader business.

Phase 1 is a **fleshed-out internal product** the co-founder uses to triage cell-tower
ground-lease renegotiation candidates across the 4 anchor states. He opens it, filters,
ranks, picks targets, uploads leases as he gets them, marks lead status, and calls
landowners. Not a demo, not a customer-facing app.

**Outcome bar:** the co-founder uses the product as his **primary daily triage tool for 4
consecutive weeks**, picking targets from it without falling back to spreadsheets or asking
the dev for custom data pulls. Deal-closing is outside the gate (depends on his pitching +
the market); usage is the honest proxy. The 4-week clock starts after Slice B ships.

---

## 2. Anchor geographies (locked) — canonical

| State | FIPS | Role | Status |
|---|---|---|---|
| **Arkansas** | 05 | Primary state | Composed; 2.1M parcels; full owner data |
| **Montana** | 30 | Western proof point | Composed; 920K parcels; rural-tower representative |
| **Florida** | 12 | Anchor | Composed (28 GB raw, all 67 counties); live in app |
| **West Virginia** | 54 | Anchor (Appalachian distress) | Composed (1.39M parcels, all 55 counties); live in app |

The four **committed anchors are AR + MT + FL + WV.** West Virginia (54) was elevated from
candidate to committed anchor on 2026-05-29 ([ADR-060](./adr/0060-wv-committed-anchor.md))
— added as a live, composed source (`wv_parcels`, WVGISTC statewide `.gdb`, SB 588) and
ranked #5 of 51 in the 2026-05-27 50-state review. WV parcel = **surface** owner
(split-estate is the norm in rural WV — do not conflate with mineral ownership).

**Deferred / Phase-1 stretch:** **North Carolina** (37, the original pilot context) — all
raw deleted 2026-05-20; re-fetch + normalize + compose **deferred** (NC OneMap re-fetch
intermittently 504s). A future stretch candidate, **not a committed anchor.**

**Dropped** (won't appear in Phase 1): **IN** + **UT** (no owner data — ADR-017, ADR-049);
**MN** (license ambiguity — ADR-018).

Phase 2 may add states with dense rooftop volume; see
[ADR-054](./adr/0054-asset-universe-phase-1-2.md).

---

## 3. Phase 1 slice plan (in order) — canonical

Untimed — goal-driven, not calendar-driven. Each slice has a "shipped" gate (§4). For where
each slice stands **today**, see [STATUS.md](./STATUS.md).

| # | Slice | Rough cost |
|---|---|---|
| **F** | Committed anchors (AR + MT + FL + WV) composed (chunked compose, ADR-051). NC re-fetch deferred. | ~2 wks |
| **A** | FCC ULS carrier identification (Cellular + PCS + AWS/700) | 2–3 wks |
| **C** | Asset enrichment (billboards + solar on parcel) + tunable scoring UI | 2–4 wks |
| **D + E** | Lease-doc upload + LLM extraction + triage write layer + CSV exports. **Backend stands up here** (ADR-055). | 4–6 wks |
| **B** | Vendor (tower-co) inference — ASR registrant + portfolio roll-up heuristic | 1–2 wks |

After Slice B, the **4-week outcome-bar clock** starts.

> **Reordered 2026-05-30:** the D+E write-layer + lead-centric triage UI were pulled forward
> ahead of A and C and shipped ([ADR-061](./adr/0061-lead-centric-triage-redesign.md)); the
> remaining D+E work is lease-doc upload + LLM extraction (ADR-059, not started). See
> STATUS for the live picture.

---

## 4. Per-slice "shipped" gates

| Slice | Gate |
|---|---|
| **F — anchor composes** | Each committed anchor composes with 0 warnings, all **11 joins** applied, all **8 views** built; FL recomposed (county-score gap closed) + WV added & composed. Peak memory < 14 GB (proves chunked compose). NC re-fetch deferred — does not gate. |
| **A — carriers** | ⚠️ **Coverage bar overtaken by measured reality.** Original gate: ≥ 70% of FCC ASR towers carry ≥ 1 carrier. **Actual ~6–17%** per anchor — the ULS↔ASR join is high-precision / low-recall (most ASR structures have no per-site ULS license), so coverage is bounded by the *source*, not the join. **Met:** join tolerance calibrated + documented; carrier list with confidence tags in the tower lead-detail panel. The empty carrier list is the common case and reads as normal, not an error. |
| **C — billboards + solar + tunable UI** | `has_billboard` + `has_solar` populated for anchors; app ships tunable scoring sliders + per-parcel components breakdown; co-founder runs a triage session end-to-end without the dev. |
| **D + E — lease docs + triage state** | Auth working; lead state persists across sessions; lease PDF → structured extraction with per-field confidence; ≥ 85% field accuracy on a hand-labelled 20-lease gold-set; CSV export covers every field in the co-founder's wishlist. |
| **B — vendor inference** | `vendor_best_guess` populated for ≥ 60% of towers; confidence tag shown. |

**Per-slice test-coverage bar:** ≥ 70% line coverage of new code shipped in each slice.

---

## 5. In-scope data sources

Per-source schema / license / policy is in [DATA_SOURCES.md](./DATA_SOURCES.md).

**Already in pipeline** (AR/MT/FL/WV composed; NC deferred): FCC ASR (tower locations), FAA
OEAAA (proposed/recent tall structures), state parcel layers (AR GIO, MT Cadastral, FDOR
NAL per-county for FL, WVGISTC for WV; NC OneMap deferred), HUD Opportunity Zones + QCT, ARC
distressed counties, USDA persistent poverty, EIA Form 860/860M + USPVDB (utility-scale
solar).

**Phase 1 additions** (flipped from earlier deferrals): FCC ULS — Cellular (Part 22) + PCS
(Part 24) + AWS / 700 MHz (Part 27) for carrier ID (Slice A — **shipped**); state DOT
billboard permits (Slice C); Steel-in-the-Air free county-level lease-rent benchmarks +
Secretary-of-State business-entity records + UCC-1 filings (Slice D — not started).

---

## 6. Out of scope / anti-goals (Phase 1)

Where we deliberately under-invest. (Permanent non-goals are flagged.)

| Item | Status / why |
|---|---|
| **Rooftop installations** + supporting data (CoStar / LoopNet / building mortgage / tenant mix) | **Phase 2** ([ADR-054](./adr/0054-asset-universe-phase-1-2.md)) — different asset universe, mostly paid |
| **Nationwide coverage** | Phase 2+ — 4 anchor states only; nationwide is paid Regrid ([ADR-012](./adr/0012-regrid-deferred.md) / [ADR-057](./adr/0057-budget-posture-reframed.md)) |
| **Paid skip-trace / mortgage / building-tenant data** | Phase 2+ — current-budget posture ([ADR-057](./adr/0057-budget-posture-reframed.md)) |
| **LLC unmasking beyond SoS officer disclosure** | **Permanent non-goal** (ADR-041 narrowed via ADR-057) — sensitive, FCRA-adjacent |
| **Mass email / CRM-style outreach automation** | Phase 2 — surface the lead, log activity, export CSV; the actual call/email lives outside the product |
| **Carrier-side features** | Out — this is a landowner-side tool |
| **Real-time data** | Out — manual-trigger pulls; freshness surfaced in UI |
| **Multi-tenant traffic** | One tenant today, but the schema is tenant-shaped from Day 1 ([ADR-055](./adr/0055-hosted-private-backend.md)) |
| **Performance optimization beyond "fast enough"** | Phase 1 means usable, not benchmarked |
| ULS Microwave / Ownership / Transfers / Leasing | Deferred to Slice B or Phase 2 — backhaul / vendor-inference signal, not carrier presence |
| `hifld_towers` | Removed from the repo 2026-07-03 ([ADR-015](./adr/0015-hifld-towers-retired.md)) — DHS retired the layer in 2024; dead code deleted |

---

## 7. Data-freshness UX policy

How freshness surfaces to the co-founder:

- **Top of triage list:** per-state last-refresh badge, e.g. *"Last full data refresh: AR
  12d, MT 9d, FL 47d, WV 18d"*.
- **Per-lead detail panel:** per-source dates (parcel / tower / lease-comp).
- **Hard banner** when a state's parcel source is > 180 days old (parcels are the
  lead-discovery substrate). **Soft warning** for stale ULS / distress overlays.
- **Refresh trigger (Phase 1):** dev-only — the dev runs the puller; the co-founder sees the
  resulting dates. Self-serve refresh is Phase 2.

MANUAL_ONLY sources (FDOR NAL = 67 FL counties, click-through each) need the dev at every
refresh. Phase 1 does not fix this; see [DATA_FRESHNESS.md](./DATA_FRESHNESS.md).

---

## 8. Phase 1 architecture decisions

| ADR | What it locks |
|---|---|
| [ADR-053](./adr/0053-product-phase-shift.md) | Pitch → product; outcome bar; in-scope feature flips |
| [ADR-054](./adr/0054-asset-universe-phase-1-2.md) | Freestanding-only Phase 1; rooftops Phase 2 |
| [ADR-055](./adr/0055-hosted-private-backend.md) | Backend + tenant-shaped schema Day 1; supersedes ADR-006 |
| [ADR-056](./adr/0056-lead-equals-owner-cluster.md) | Lead = owner-cluster; cluster-score rollup |
| [ADR-057](./adr/0057-budget-posture-reframed.md) | ADR-010 reframed; ADR-041 narrowed to paid skip-trace only |
| [ADR-058](./adr/0058-tunable-transparent-scoring.md) | Client-side tunable scoring + presets |
| [ADR-059](./adr/0059-llm-lease-extraction.md) | LLM lease extraction (hybrid citation + self-rated confidence) |
| [ADR-060](./adr/0060-wv-committed-anchor.md) | WV elevated to a committed anchor |

The full decision index is [DECISIONS.md](./DECISIONS.md).

---

## 9. The five questions a teammate should answer in 15 minutes

A non-technical teammate (or future-you) reading the docs should be able to answer:

1. **What does this product do?** → §1 + [PROJECT_BRIEF.md](../PROJECT_BRIEF.md)
2. **Current state — what works, what doesn't?** → [STATUS.md](./STATUS.md)
3. **How does the co-founder use it day-to-day?** → §1 + the slice gates (§4)
4. **What are the limitations and risks?** → [LIMITATIONS.md](./LIMITATIONS.md) + [SECURITY.md](./SECURITY.md)
5. **What's next, and why does it cost what it costs?** → [ROADMAP.md](./ROADMAP.md)

If they can't get all five from the docs alone, the docs aren't done.

---

## 10. Where to look next

- **What state we're in today** → [STATUS.md](./STATUS.md)
- **What shipped when** → [CHANGELOG.md](./CHANGELOG.md)
- **Future (Phase 2/3)** → [ROADMAP.md](./ROADMAP.md)
- **Locked design decisions** → [DECISIONS.md](./DECISIONS.md) + [`docs/adr/`](./adr/)
- **How the system fits together** → [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Per-source detail** → [DATA_SOURCES.md](./DATA_SOURCES.md)
- **Product language** → [../GLOSSARY.md](../GLOSSARY.md) + [GLOSSARY.md](./GLOSSARY.md)
- **Caveats + pre-commercial blockers** → [LIMITATIONS.md](./LIMITATIONS.md)
- **PII / data-handling** → [SECURITY.md](./SECURITY.md)
