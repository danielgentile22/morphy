# GOALS — What Success Looks Like

**Last updated:** 2026-05-25
**Status:** Phase 1 product cut
**Supersedes:** the previous pitch-cut GOALS.md (2026-05-20)
**Pairs with:** [SCOPE.md](./SCOPE.md), [STATUS.md](./STATUS.md), [ROADMAP.md](./ROADMAP.md)

---

## 1. North star

A business that **moves real economic value to the landowner side of infrastructure ground-leases** — primarily cell towers — by using public + private data to identify, prioritize, and equip landowners with the information they need to renegotiate undervalued contracts or evaluate unsolicited buyout offers.

The product in this repo is the **co-founder's working tool** to do that triage and contract analysis. It's the foundation layer of the broader business.

---

## 2. Phase 1 product cut (this push)

The current push produces a tool the **co-founder uses daily** to triage cell-tower ground-lease renegotiation candidates across 4 anchor states.

This is no longer a pitch-quality demo (see [ADR-053](./adr/0053-product-phase-shift.md)). The audience is the co-founder; he opens the app, filters parcels, ranks, picks targets, uploads leases as he gets them, marks lead status, and calls landowners.

**Outcome bar:** the co-founder uses the product as his **primary daily triage tool for 4 consecutive weeks**, picking targets from it without falling back to spreadsheets or asking the dev for custom data pulls.

Deal-closing is outside the gate — depends on the co-founder's pitching, market conditions, paid skip-trace decisions further out. Usage is the honest proxy.

---

## 3. Per-slice "shipped" gates

| Slice | Gate |
|---|---|
| **F — finish FL+NC** | FL + NC each compose with 0 warnings, all 9 joins applied, all 8 views built. Peak memory < 14 GB (proves chunked compose works). NC fetch resumable across restarts. |
| **A — carriers** | ≥ 70% of FCC ASR towers in anchor states have ≥ 1 carrier identified. Carrier list in lead-detail panel. ULS↔ASR join tolerance documented. |
| **C — billboards + solar + tunable UI** | `has_billboard` + `has_solar` populated for anchor states. Map app ships tunable scoring sliders + per-parcel components breakdown. Co-founder runs a triage session end-to-end without dev next to him. |
| **D + E — lease docs + triage state** | Auth working; lead state persists across sessions. Lease PDF upload → structured extraction with per-field confidence. ≥ 85% field accuracy on hand-labelled 20-lease gold-set. CSV export covers every field in cofounder's wishlist. |
| **B — vendor inference** | `vendor_best_guess` populated for ≥ 60% of towers; confidence tag shown. |

**Per-slice test-coverage bar:** ≥ 70% line coverage of new code shipped in each slice. Lifts overall coverage gradually rather than retrofitting at the end.

---

## 4. The five questions a teammate should answer in 15 min

A non-technical teammate (or future-you next quarter) reading the docs should be able to answer:

1. **What does this product do?** *(SCOPE.md + PROJECT_BRIEF.md front matter)*
2. **What's the current state — what works, what doesn't?** *(STATUS.md)*
3. **How does the co-founder use it day-to-day?** *(SCOPE.md §3 + the slice gates above)*
4. **What are the limitations and risks?** *(LIMITATIONS.md + SECURITY.md)*
5. **What's next, and why does it cost what it costs?** *(ROADMAP.md)*

If they can't get all five from the docs alone, the docs are not done.

---

## 5. Anti-goals (where we deliberately under-invest in Phase 1)

- **No rooftop installations** — Phase 2 ([ADR-054](./adr/0054-asset-universe-phase-1-2.md)).
- **No nationwide coverage** — 4 anchor states; nationwide is paid Regrid.
- **No paid skip-trace, mortgage data, building tenant data** — current-budget posture ([ADR-057](./adr/0057-budget-posture-reframed.md)).
- **No mass email or CRM automation** — Phase 2.
- **No real-time data** — manual-trigger pulls; freshness surfaced in UI.
- **No multi-tenant traffic** — single tenant, but schema is tenant-shaped from Day 1 ([ADR-055](./adr/0055-hosted-private-backend.md)).
- **No performance optimization beyond "fast enough"** — Phase 1 means usable, not benchmarked.

---

## 6. Phase 2 goals (not for this cut — see [ROADMAP.md](./ROADMAP.md))

Documented here so they don't accidentally creep into Phase 1:

- Rooftop / in-building asset universe (ADR-054)
- Mass-email + response tracking
- Self-serve refresh from the product
- Recorded-lease automation for top counties
- Paid Steel-in-the-Air tier (granular per-tower comps)
- Paid skip-trace integration (contact phone / email)
- Paid mortgage / financial-distress signal
- Nationwide via Regrid (paid)
- Multi-tenant hosting (Phase 3 — sell to other land-side consultants)

---

## 7. How we know we're trending right

Each Slice ends with its gate check. If gates F → A → C → D+E → B pass in order, the outcome bar (primary daily tool, 4 weeks) follows naturally — and is the canonical "Phase 1 done" signal.

Re-read this doc whenever "should we do X right now?" comes up. If X is not in service of getting the co-founder to the daily-tool outcome, the answer is almost certainly no.
