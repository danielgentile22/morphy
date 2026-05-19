# GOALS — What Success Looks Like

**Last updated:** 2026-05-19
**Pairs with:** [SCOPE.md](./SCOPE.md) (what we're building) and
[STATUS.md](./STATUS.md) (where we are today).

---

## 1. North star

A business that **moves real economic value to the landowner side of
infrastructure ground-leases** — primarily cell towers — by using free
public data to identify, prioritize, and equip landowners with the
information they need to renegotiate undervalued contracts or evaluate
unsolicited buyout offers.

The data work in this repo is the *foundation* of that business. It
exists to answer the question every other layer depends on: *given a
piece of infrastructure, who owns the land under it, and how
prioritizable is that landowner for outreach?*

---

## 2. v1 cut (this push): pitch-quality demo

Success for the current push is producing an artifact a co-founder /
investor / strategic partner can be walked through in 10 minutes that
*defensibly* shows:

1. The data linkage problem is real and structurally solvable.
2. We can do it across multiple states with only free data.
3. The output surfaces specific high-value, prioritizable opportunities
   (not just a heatmap).
4. The technical foundation is reproducible, tested, version-controlled,
   and documented well enough that a partner can read the repo and
   understand what's been built without us in the room.

This is the **only** thing this push optimizes for. We are explicitly
not optimizing for: customer-facing UX, scale to all 50 states, or
commercial-deployment readiness.

---

## 3. The five questions a partner should be able to answer in 15 min

A non-technical partner reading the docs (without us walking them
through) should be able to answer:

1. **What does this project do?** *(SCOPE.md + GOALS.md + PROJECT_BRIEF.md
   front matter)*
2. **What's the current state — what works, what doesn't?** *(STATUS.md)*
3. **What can be demoed today?** *(SCOPE.md §5 + pitch-assets/)*
4. **What are the limitations and risks?** *(LIMITATIONS.md + SECURITY.md)*
5. **What's next, and why does it cost what it costs?** *(ROADMAP.md)*

If they can't get all five from the docs alone, the docs are not done.

---

## 4. KPIs (measurable success criteria for this cut)

| KPI | Target | Where it's measured |
|---|---|---|
| **Anchor-state coverage** | 4 of 5 anchor states composed cleanly (AR + NC + MT + UT minimum; FL stretch) | `data/processed/composite/<fips>/summary.json` for each — `joins_applied` length = 9, `warnings` empty |
| **Composite freshness** | Every anchor state's raw inputs ≤ 90 days old at pitch time | `data/manifest.json` `fetched_at` per source vs. today |
| **View completeness** | ≥ 8 views built per state with owner data (AR/NC/MT/UT) | `summary.json` `views_built` length |
| **Tests** | ≥ 30 tests passing; ≥ 70 % line coverage of `scripts/preprocess/` | `pytest --cov=scripts.preprocess` |
| **CI green** | Every push to `main` has lint + tests green | GitHub Actions badge on README |
| **Doc currency** | Every doc in `docs/` has `Last updated:` within 30 days at pitch time | Header on each `.md` file |
| **Demo scenarios captured** | 3 of 3 documented in NUMBERS.md with screenshots in `docs/pitch-assets/` | File presence + manual review |
| **Puller UX** | Every MANUAL_ONLY anchor source has a working walkthrough modal with ≥ 3 ordered steps + deep link + expected files | Manual click-through verification |
| **Defensibility** | Every figure in INVESTOR_BRIEF.md traces to a parquet path + query in NUMBERS.md | Audit: random-sample 5 numbers, follow them |

---

## 5. Anti-goals (where we deliberately under-invest)

These are areas where we explicitly accept lower quality during this
cut, to avoid scope creep:

- **Map UX.** The current Leaflet app is functional but has known gaps
  (no useful filters for v3 fields, can't load huge parcel layers).
  We apply only minimal patches; the full rebuild is in
  [MAP_APP_REHAUL.md](./MAP_APP_REHAUL.md) and deferred.
- **Production deployment.** Local-only is fine. No Docker, no cloud,
  no hosted instance.
- **Real-time data.** All ingest is batch + manual-trigger. No
  streaming, no daemons, no cron.
- **Multi-user access.** Single dev today. Access controls / audit
  trails wait for the post-pitch product phase.
- **Performance beyond "fast enough."** Preprocess that runs in < 5
  min per state is acceptable; further optimization is not goal-state.
- **Coverage breadth.** 3–5 anchor states is enough. Nationwide is a
  paid-data conversation.

---

## 6. Post-pitch goals (not for this cut — see ROADMAP for detail)

Documented here only so they don't accidentally creep into this cut:

- Full map app rehaul (MapLibre + PMTiles + DuckDB-WASM)
- FCC ULS normalizers + carrier/tenant analytics
- Billboards as a second asset class
- LLC-cluster enrichment (Secretary of State, UCC-1 filings)
- Distress-signal layering (tax delinquency, foreclosure pre-filings)
- Nationwide coverage via Regrid (paid)
- Hosted deployment + multi-user access controls
- Outreach workflow (CRM, scheduling, contact data)

---

## 7. How we know we're trending the right way

Each section of the work plan ends with a verification checklist. If
those checklists are passing in order, the KPIs above will be green by
the end. The single end-to-end check at the bottom of the plan file is
the canonical "we're done with this cut" gate.

Re-read this doc whenever the question "should we do X right now?"
comes up. If X is not in service of one of the KPIs in §4, the answer
is almost certainly no.
