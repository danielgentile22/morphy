# STATUS — Where the project stands today

**Last updated:** 2026-07-03
**Update cadence:** at the start of every slice and at every session handoff.

A snapshot of *current* reality. If this disagrees with the code or data, the code/data
wins — fix the doc. The **canonical scope + slice plan + anchor list live in
[SCOPE.md](./SCOPE.md)**; the **milestone trail (what shipped when) lives in
[CHANGELOG.md](./CHANGELOG.md)**; the **future lives in [ROADMAP.md](./ROADMAP.md)**. This
doc is current-state-only.

---

## 1. TL;DR

**The product is live in production** ([morphyconsulting.com](https://morphyconsulting.com))
and well past Phase 1's midpoint. The backend (`backend/` — tenant-scoped FastAPI +
SQLAlchemy over the cross-state owners-index precompute `scripts/preprocess/owners_index.py`,
`--owners-index`) carries Leads + Tasks behind username/password auth; the three-section
app (Dashboard · Explore · Leads), now on the dark **"Halo"** design system, is the daily
surface.

**Shipped:** Slices **F, A, C**, and **most of D+E** — the lead-centric redesign, the UI
overhaul, auth, the #130–#138 hardening pass, the data-audit catalog at `/audit/`, and Ask
Claude. (Trail in [CHANGELOG.md](./CHANGELOG.md).)

**Deployed 2026-07-04:** the data-audit follow-through — 7 MACRO/HITL data-quality fixes
([ADR-070](./adr/0070-statutory-assessed-value.md)–[076](./adr/0076-owner-type-classifier.md))
— is live in prod (composites regen'd via the data TUI + `deploy.sh data --apply`), plus a
same-day hotfix (PR #281) for a #221 tower-cid regression that had collapsed the map's tower
layer (§4.5).

**Next up:** the rest of **D+E** — lease-doc upload + LLM extraction + R2 storage (per
[ADR-059](./adr/0059-llm-lease-extraction.md); **not started** — no lease/extraction code on
disk) — then **Slice B** (vendor inference). The 4-week outcome-bar clock starts after B.

| State | Raw | Normalized | Composed | Notes |
|---|---|---|---|---|
| **AR** (05) | ✅ | ✅ 2,116,976 parcels | ✅ 11 joins, 8 views, 0 warnings | Audited clean 2026-05-21. |
| **MT** (30) | ✅ all 56 counties | ✅ 920,111 parcels | ✅ 11 joins, 8 views, 0 warnings | Audited clean 2026-05-21. |
| **FL** (12) | ✅ all 67 counties (~28 GB) | ✅ 11,184,113 parcels (fdor_nal) | ✅ 11,425,608 parcels, 11 joins, 8 views, 0 warnings | Live in app; county-score gap closed 2026-05-29 (§4.1). |
| **WV** (54) | ✅ statewide `.gdb` (WVGISTC, SB 588) | ✅ 1,389,855 parcels | ✅ 11 joins, 8 views, 0 warnings | Committed anchor (ADR-060); live in app (§4.2). |
| **NC** (37) | ❌ deleted 2026-05-20 | ❌ | ❌ | ⏸️ Deferred Phase-1 stretch — not a committed anchor (§4.3). |

`index.json` lists 05, 12, 30, 54. Committed anchors: **AR + MT + FL + WV** (see
[SCOPE.md §2](./SCOPE.md)).

---

## 2. What works

- **AR + MT + FL + WV end-to-end** — pull → normalize → compose → 8 views, joined to
  national towers + ARC/HUD/USDA distress. All four live in the app.
- **The production stack** — Fly single always-on machine (`morphy-consulting`), SQLite +
  Litestream→R2, Cloudflare Full-strict ([ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md));
  `/data/processed/*` edge-gated by `forward_auth` (ADR-069); `deploy.sh smoke` asserts the
  unauth data plane stays 401/403.
- **The backend** (`backend/`) — Leads + Tasks + activity + scoring presets/settings + owner
  merge/split, username/password auth (creds in the DB `credential` table, identity-only JWT,
  teams-as-tenants; ADR-062/063/069). 12 SQLAlchemy tables; Alembic migrations
  (head `0002_ask_log`).
- **Slice A carriers** — ULS↔ASR `carriers` on every tower (owners index → schema v4);
  carrier-list UI with confidence badges. Coverage ~6–17% of ASR towers (high-precision /
  low-recall) — an empty list is normal. *(The MACRO-1 rework that surfaces the modern
  spectrum bands is live as of the 2026-07-04 deploy — §4.5.)*
- **Slice C tunable scoring** — per-tower `score` (owners index → **schema v10** live as of
  the 2026-07-04 data-audit deploy, §4.5), tunable live re-rank, named presets.
  Solar→parcel done (`SolarToParcelJoin`; `has_solar` / `solar_count` on AR/MT/FL).
- **The data TUI** (`python -m data_tui`, PRD #233; shipped 2026-07-03) — *the* puller:
  full lifecycle pull → preprocess → verify → confirm-gated data deploy from one terminal
  app, over the unchanged headless `fetch`/`preprocess` libraries + `deploy.sh`. 16/17
  active sources auto-fetch (AR parcels manual until its ~2027-05 refresh; `w`/`i` cover
  the manual path). The Qt puller + PySide6 pin were deleted in #240 (PRD #138 retirement
  clause); the dead HIFLD source was removed and FL FGDL DSL (state-owned land) was
  re-activated as an auto-fetch complement to FDOR NAL (2026-07-03).
- **Preprocess pipeline** — v3 Normalizer→Join→View→Compose framework over **DuckDB** as the
  heavy-lift engine (PRD #135; `scripts/preprocess/duck.py` owns connections), chunked
  compose (ADR-051, the only compose path), one annotator per parcel/infra concept.
- **Map app** at `app/` — Svelte 5 + MapLibre + PMTiles + DuckDB-WASM; reads catalog-driven
  composites for any composed state; MapTiler Satellite Hybrid default basemap.
- **Data-audit catalog** — standalone `audit-site/` Svelte app, live at
  `morphyconsulting.com/audit/` (gated by the same `forward_auth` as `/data/processed/*`),
  browsing `docs/research/data-audit/`. Includes a live "Fixes" tab.
- **Ask Claude** (PRD #187) — in-catalog streaming LLM helper, the backend's first SSE stream
  (`POST /api/audit/ask`, `ask_log` table). Deployed but **dormant until the
  `ANTHROPIC_API_KEY` Fly secret is set** (clean 503 meanwhile).

---

## 3. What does NOT work / is incomplete

| Item | State | Detail |
|---|---|---|
| Lease-doc upload + LLM extraction | ⬜ Rest of D+E | Per [ADR-059](./adr/0059-llm-lease-extraction.md). 20-lease gold-set first. **Not started** — no lease/extraction code on disk. |
| Vendor inference | ⬜ Slice B | ASR registrant + portfolio rollup. Lowest Phase 1 priority. |
| Billboards | 🟡 Registered no-op | `fdot_/ncdot_/txdot_billboards` normalizers + `BillboardToParcelJoin` are registered (deferred sources), but billboard raw isn't populated for the anchors, so the join runs as a no-op (#13). |
| NC (37) | ⏸️ Deferred | Raw deleted 2026-05-20; re-fetch from NC OneMap deferred (endpoint 504s). Not a committed anchor (§4.3). |
| LLM eval suite | ⬜ | The ADR-059 gold-set accuracy harness is the genuinely-unbuilt test surface ([TESTING.md](./TESTING.md)). |

The backend + UI test suites have shipped (backend `LeadStore` / multi-tenancy isolation /
status-machine / merge-split, the frontend `FilterModel`/Vitest suites) — see
[TESTING.md](./TESTING.md) and [backend/AGENTS.md](../backend/AGENTS.md).

---

## 4. Known issues — detail

### 4.1 FL — county-score gap closed (2026-05-29)

FL was recomposed 2026-05-29 via the **chunked compose** path (ADR-051): 11,425,608 parcels
(`fdor_nal` 11,184,113 + `fl_fgdl_parcels` ~241,518), 11 joins applied (0 skipped), 8 views,
0 warnings. The earlier compose had skipped `CountyScoreToTowerJoin`/`CountyScoreToSolarJoin`
+ the standalone `county_scores` layer (it ran before the ARC/USDA normalizers finished); the
recompose ran with that data present, so FL now carries them and is consistent with AR/MT.
Reproduce: `python scripts/preprocess.py --state 12`.

### 4.2 WV — committed Phase-1 anchor (added 2026-05-29)

`wv_parcels` (WVGISTC / MapWV statewide File Geodatabase, SB 588 free bulk) → normalize
(1,389,855 parcels) → `composite/54` (11 joins, 8 views, 0 warnings; joined to national
towers + ARC/HUD/USDA distress). Two WV-specific wrinkles handled in code: (1) owner/value/
land-use live in a separate `ParcelSummary` table joined on `CleanParcelID` via an opt-in
`AttributeJoin`; (2) WV's internal `CountyID` (01–55) is **not** Census FIPS, so county
resolves via an explicit verified table, not a prefix-concat. See
`scripts/preprocess/normalizers/state_parcel_adapters/wv.py` + ADR-060. Reproduce:
`python scripts/preprocess.py --state 54`.

### 4.3 NC — deferred / Phase-1 stretch (raw deleted)

NC is **deferred** — no longer a committed anchor. Both `data/raw/nc_onemap_parcels/` and
`data/raw/NC/` were deleted 2026-05-20. NC OneMap's auto-fetch paginates ~1,186 pages; the
previous fetch stalled at page 1,106 on a server-side HTTP 504 at deep offsets (intermittent
upstream degradation, not a code bug) — part of why the re-fetch is deferred rather than
scheduled. If picked up: `python -m data_tui` (auto-fetch `nc_onemap_parcels` — the source
opts into resumable partials, so a stall mid-pagination resumes instead of restarting), then
normalize + compose via the chunked path.

### 4.4 Stale on-disk items

- `composite/18` and `normalized/in_parcels` — IN dropped from this cut (ADR-017); safe to
  delete.

### 4.5 Data-audit follow-through — shipped + deployed (2026-07-04)

The data audit's actionable findings shipped their **code** in a batch (ADRs
[070](./adr/0070-statutory-assessed-value.md)–[076](./adr/0076-owner-type-classifier.md);
issues #213/#217/#218/#219/#220/#221/#222), all merged to `main` by 2026-07-03, then **regen'd +
deployed to prod 2026-07-04** (composites rebuilt via the data TUI, synced with
`deploy.sh data --apply`):

- **MACRO-1 / #220** ([ADR-074](./adr/0074-uls-carrier-rearchitecture.md)) — ULS→carrier rework.
  The market-band drop is fixed (a `load_state_data` override — PCS/AWS/700 now flow, so
  T-Mobile / Dish / Verizon-market can attach via the proximity fallback); the dead ULS
  `entity` layer dropped (M-e); the badge reframed **"Licensed in this area — not a confirmed
  tenant."** The before/after unmapped-carrier rate is measured at regen.
- **MACRO-6 / #221** ([ADR-075](./adr/0075-cross-state-owner-identity.md)) — cross-state owner
  key changed name-only → **name + state**, with a curated towerco alias table (Crown Castle /
  American Tower / SBA / Vertical Bridge) re-merging across states. Owners-index **schema
  v9→v10**. Validated read-only on real data: **64** same-name-different-state false-merges
  split, and **exactly the 4 curated towercos** stay national (nothing else spans states).
- **MACRO-2/3/5/7 + M-k** — FAA↔ASR tower dedup (+`faa_corroborated`, #219), solar-feed dedup
  by EIA plant code (#217), the reweighted default score preset (+owner `carrier_count`, #218),
  the expanded owner-type classifier (towerco/utility/nonprofit, #222), and statutory assessed
  value surfaced alongside market (#213). The owners-index schema climbed **v5 → v10** across
  the batch.

**Post-deploy hotfix — #221 tower-cid regression (PR #281, deployed 2026-07-04).** The v10
name+state key was only applied in `owners_index.py`; `national_towers.py` still baked each
tower's `cid` (in `towers.json`) with the old **name-only** key. The map narrows its tower layer
by the owners-index id set, so tower cids and index ids diverged (only the 4 curated towercos
overlapped) and the layer collapsed — ~400 towers shown in WV, every state hit. **Not data
loss** (all towers stayed in the composite). Fixed by baking `cross_state_owner_key(name,
state_fips)`; verified 100% cid overlap (WV 2663/2663, 5,722 towers resolve to a landowner) and
shipped `towers.json`-only (no parcel reprocess, no lead remap). Lesson: the cross-state key
recipe has **two producers** (`owners_index.py` + `national_towers.py`) — the parity test pinned
`national_towers`↔client to each other, not to the owners index, so the drift slipped the batch.

Live per-fix board: the **Fixes tab** at `/audit/` (`docs/research/data-audit/fixes.json` +
`fix-ledger.md`). Research-first items still open: #223 (AR owner-mailing feed), #224 (FL
billboards); #212 (M-h, FL NAL owner-name) is blocked on a manual download.

---

## 5. Phase 1 slice progress

The canonical slice plan + per-slice gates live in [SCOPE.md §3–§4](./SCOPE.md). Live state:

| Slice | State |
|---|---|
| **F** — Anchor composes (AR + MT + FL + WV) | 🟢 Shipped — committed anchors composed; NC compose deferred (§4.3). |
| **A** — FCC ULS carrier identification | 🟢 Shipped — data layer (#11/#12/#22/#24) + carrier-list UI (#28). Coverage ~6–17% (the original "≥70%" gate is overtaken by measured reality — [SCOPE.md §4](./SCOPE.md)). |
| **C** — Asset enrichment + tunable scoring UI | 🟢 Shipped — per-tower scoring (#105), tunable re-rank (#114), named presets (#115); solar→parcel done (#14). Billboards a registered no-op (#13). |
| **D + E** — Lease docs + triage state + backend | 🟡 Partial — backend + redesigned UI shipped & deployed; **lease-doc upload + LLM extraction (ADR-059) not started.** |
| **B** — Vendor inference | ⬜ Not started. |

---

## 6. Outstanding decisions for the user

| Item | Notes |
|---|---|
| **Verify the #221 owner-key remap ran** (§4.5) | The v10 recipe change re-hashes every `display_cluster_id`. The composites + tower-cid hotfix are deployed, but confirm the one-time `python -m app.remap_owner_clusters` ran on the prod DB (DEPLOYMENT.md §8) — if it didn't and prod carries `Lead`/`ContactAttempt`/`OwnerClusterOverride` state, those rows are orphaned under the old keys. The chosen policy is the **one-shot remap** (idempotent; safe to run/re-run). Product change to note: a national owner (e.g. Weyerhaeuser AR+WV) now shows as **two** Leads unless it's a curated towerco. |
| Steel-in-the-Air free dataset — **premise overturned 2026-05-26** | The free county-level lease-rate dataset doesn't exist (`docs/research/reports-2026-05-26/INDEX.md`). Slice D `lease_comp` source-of-truth needs a replacement — next-best free path is REIT 10-K rent disclosures + ABS securitization filings. Paid Steel-in-the-Air tier is the Phase 2 unlock ([ADR-057](./adr/0057-budget-posture-reframed.md)). |
| libpostal vs `usaddress` for owner-clustering address normalization | Deferred owner-resolution refinement (#26) — **not** in scope for the shipped name-anchored matching, and **superseded as the day-1 fix by the manual merge/split net** (#53, shipped). Lean libpostal; fall back to `usaddress` if dep-management is painful. |
