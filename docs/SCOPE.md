# SCOPE — Phase 1 Product

**Last updated:** 2026-05-29 (FL recomposed — county-score gap closed)
**Status:** Active — Phase 1 in progress
**Owner of this doc:** Whoever is currently driving the project (single dev today)
**Supersedes:** the previous "v1 Pitch / Demo Cut" SCOPE.md (2026-05-20)

This document is the **single source of truth for "what we are building right now."** Anything not listed here is out of scope for Phase 1.

For the strategic pivot from pitch demo → product, see [ADR-053](./adr/0053-product-phase-shift.md). Phase 2 lives in [ROADMAP.md](./ROADMAP.md).

---

## 1. What Phase 1 is

A **fleshed-out internal product** the co-founder uses to triage cell-tower ground-lease renegotiation candidates across 3 anchor states. The audience is *the co-founder* — he opens it, filters, ranks, picks targets, uploads leases as he gets them, marks lead status, and calls landowners. Not a demo, not a customer-facing app.

**Outcome bar:** the co-founder uses the product as his **primary daily triage tool for 4 consecutive weeks**, picking targets from it without falling back to spreadsheets or asking the dev for custom data pulls. Deal-closing is outside the gate (depends on his pitching + market); usage is the honest proxy.

---

## 2. Anchor geographies (locked)

| State | FIPS | Role | Today |
|---|---|---|---|
| **Arkansas** | 05 | Primary state | Composes cleanly; 2.1M parcels; 222K LLCs; full owner data |
| **Montana** | 30 | Western proof point | Composes cleanly; 920K parcels; rural-tower representative |
| **Florida** | 12 | Anchor | Recomposed 2026-05-29 (28 GB raw, all 67 counties); live in app; county-score gap closed — consistent with AR/MT |

The three committed anchors are AR + MT + FL.

**Deferred / Phase-1 stretch:** **North Carolina** (37, original pilot context) — all raw deleted 2026-05-20; re-fetch + normalize + compose **deferred** (NC OneMap re-fetch intermittently 504s). Still in the picture as a future stretch candidate, not a committed anchor.

Dropped entirely (won't appear in Phase 1): **IN** + **UT** (no owner data — ADR-017, ADR-049); **MN** (license ambiguity — ADR-018).

Phase 2 may add states with dense rooftop volume; see [ADR-054](./adr/0054-asset-universe-phase-1-2.md).

---

## 3. Phase 1 slice plan (in order)

Untimed — goal-driven, not calendar-driven. Each slice has a "shipped" gate before moving to the next. See [GOALS.md §3](./GOALS.md) for the gates.

| # | Slice | Cost (rough) |
|---|---|---|
| **F** | Committed anchors (AR + MT + FL) composed — FL recomposed 2026-05-29, county-score gap closed (chunked compose ADR-051). NC re-fetch + compose **deferred** to a Phase-1 stretch — not gating this slice. | ~2 wks |
| **A** | FCC ULS carrier identification (Cellular + PCS + AWS/700) | 2–3 wks |
| **C** | Asset enrichment (billboards + solar on parcel) + **tunable scoring UI** | 1-2 wks normalizers + 1-2 wks UI |
| **D + E** | Lease doc upload + LLM extraction + triage state / write layer / CSV exports. **Backend stands up here** (ADR-055). | 4-6 wks |
| **B** | Vendor (tower-co) inference — ASR registrant + portfolio roll-up heuristic | 1-2 wks |

After Slice B, the **4-week outcome-bar clock** starts.

---

## 4. In-scope data sources

### Already in pipeline (AR/MT/FL composed; NC deferred)

- **FCC ASR** — federal Antenna Structure Registration (≥ 200 ft or near airports). Authoritative point locations.
- **FAA OEAAA** — proposed and recently-built tall structures.
- **State parcel layers** — AR Geographic Information Office (AR), MT Cadastral (MT), FDOR NAL per-county (FL, all 67); NC OneMap (NC — deferred stretch state).
- **HUD Opportunity Zones** (OZ 1.0); **HUD QCT**; **ARC distressed counties**; **USDA persistent poverty**.
- **EIA Form 860 + 860M**; **USPVDB** (utility-scale solar).

### Phase 1 additions (flipped from previous deferrals)

- **FCC ULS** — Cellular (Part 22) + PCS (Part 24) + AWS / 700 MHz (Part 27) for carrier identification. ~5 GB raw on disk; ADR-013 reverses for these bands. (Slice A.)
- **State DOT billboard permits** (FL, NC raw on disk); ADR-014 partially reverses. (Slice C.)
- **Steel-in-the-Air free county-level lease-rent benchmarks** — bootstraps the comparables feature; ~3000 counties seed. Paid tier deferred to Phase 2 per ADR-057. (Slice D.)
- **Secretary of State business-entity records** (per state, free) — one-click LLC officer disclosure in lead-detail panel. ADR-057 narrows ADR-041 to allow this. (Slice D.)
- **UCC-1 filings** — surfaced in lead-detail panel for third-party-ownership clues. (Slice D.)

---

## 5. Out-of-scope this cut

| Source / feature | Status | Why deferred |
|---|---|---|
| ULS Microwave (Part 101) | Deferred | Point-to-point backhaul, not carrier-tenancy signal |
| ULS Ownership / Transfers / Leasing | Deferred to Slice B or Phase 2 | Vendor-inference signal, not core carrier-presence |
| `hifld_towers` | Retired (ADR-015) | DHS retired the layer in 2024 |
| `regrid_parcels` | Phase 2+ (paid unlock) | Free-only Phase 1; ADR-057 reframes ADR-010 |
| **Rooftop installations + supporting data** (CoStar / LoopNet / building mortgage / tenant mix) | **Phase 2** ([ADR-054](./adr/0054-asset-universe-phase-1-2.md)) | Different asset universe; mostly paid |
| Paid skip-trace (Whitepages Pro / Cole / IDI / Pipl) | Phase 2+ | ADR-057 narrows ADR-041 — paid skip-trace stays out for Phase 1 |
| Mortgage / liquidity signal | Phase 2 (paid) | CoStar / ATTOM / mortgage feeds; rooftop-flavoured asks defer with rooftops |
| Mass email + response tracking | Phase 2 | Real product surface — email infra, deliverability, CAN-SPAM; keep Phase 1 focused |
| Recorded-lease automation (Memorandum of Lease scraping) | Phase 2 | Per-county effort; cofounder pulls ad-hoc Phase 1 |
| LLC unmasking beyond SoS officer disclosure | **Permanent non-goal** (ADR-041 narrowed via ADR-057) | Sensitive, expensive, FCRA-adjacent |
| Tax-delinquency / foreclosure / REIT 10-Ks | Phase 2+ enrichments | Per PROJECT_BRIEF §8 |

---

## 6. Data freshness UX policy

How freshness surfaces to the co-founder inside the product:

- **Top of triage list:** *"Last full data refresh: AR 12d, MT 9d, FL 47d, NC 21d"* — per-state last-refresh badge.
- **Per-lead detail panel:** *"Parcel data from {date}; tower data from {date}; lease-comp data from {date}"* — per-source dates.
- **Per-source admin view** (gated, Phase 2 self-serve): refresh-trigger button.

**Staleness policy:**

- **Hard banner** when a state's parcel source is > 180 days old — the parcel layer is the lead-discovery substrate, so stale parcels mean stale leads.
- **Soft warning** for stale ULS (carriers) and distress overlays — supporting context, not lead-discovery.
- Information-only for everything else.

**Refresh trigger (Phase 1):** dev-only. The dev runs the puller; the cofounder sees the resulting dates. Self-serve refresh from inside the product is Phase 2.

**Painful reality:** MANUAL_ONLY sources (FDOR NAL = 67 Florida counties, click-through each) need the dev at every refresh. Phase 1 does not fix this. Phase 2 candidates: guided checklist UI in the puller, or paid bulk-data unlocks.

---

## 7. Hard non-goals for Phase 1

- **No rooftop installations** — Phase 2 only ([ADR-054](./adr/0054-asset-universe-phase-1-2.md)).
- **No nationwide coverage** — 3 anchor states (NC a deferred stretch).
- **No paid skip-trace / mortgage / building tenant data** — free public records only (ADR-057 narrows the older ADRs).
- **No mass email or CRM-style outreach automation** — surface the lead, log activity, export CSV; the actual call / email lives outside the product Phase 1.
- **No carrier-side features** — this is a landowner-side tool.

---

## 8. Phase 1 architecture decisions (this cut)

| ADR | What it locks |
|---|---|
| [ADR-053](./adr/0053-product-phase-shift.md) | Pitch → product; outcome bar; in-scope feature flips |
| [ADR-054](./adr/0054-asset-universe-phase-1-2.md) | Freestanding-only Phase 1; rooftops Phase 2 |
| [ADR-055](./adr/0055-hosted-private-backend.md) | Backend stands up Slice 4; tenant-shaped schema Day 1; supersedes ADR-006 |
| [ADR-056](./adr/0056-lead-equals-owner-cluster.md) | Lead = owner-cluster; cluster-score rollup; ADR-024 strengthening |
| [ADR-057](./adr/0057-budget-posture-reframed.md) | ADR-010 reframed as current budget; ADR-041 narrowed to paid skip-trace only |
| [ADR-058](./adr/0058-tunable-transparent-scoring.md) | Client-side tunable scoring + profiles in Slice 3 |
| [ADR-059](./adr/0059-llm-lease-extraction.md) | Sonnet + Opus retry, hybrid citation + self-rated confidence, direct-vision PDFs |

---

## 9. Where to look next

- **Why we're doing this** → [GOALS.md](./GOALS.md)
- **What state we're in today** → [STATUS.md](./STATUS.md)
- **Past + future** → [ROADMAP.md](./ROADMAP.md)
- **Locked-in design decisions** → [DECISIONS.md](./DECISIONS.md) (index) + `docs/adr/` (per-ADR files)
- **How the system is put together** → [ARCHITECTURE.md](./ARCHITECTURE.md) (data pipeline + Slice 4 backend)
- **Per-source detail** → [DATA_SOURCES.md](./DATA_SOURCES.md)
- **Canonical language** → `CONTEXT.md` (root)
- **Caveats and pre-commercial blockers** → [LIMITATIONS.md](./LIMITATIONS.md)
- **PII / data-handling** → [SECURITY.md](./SECURITY.md)
