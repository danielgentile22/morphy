# STATUS — Where the project stands today

**Last updated:** 2026-06-13
**Update cadence:** at the start of every slice and at every session handoff.

A snapshot of reality. If this disagrees with the code or data, the code/data wins — fix the doc.

### Recent milestones (newest first)

The canonical milestone trail. Older detail lives in git.

- **2026-06-12/13 — Phase-1 hardening, PRDs #130–#138 (all shipped).** Closed the
  unauthenticated PII data plane + moved credentials into the app DB + cookie
  sessions (#130, ADR-069); frontend CI gate (#131); uv toolchain + real packaging,
  `sys.path` hacks retired (#132); generated OpenAPI→TS types, drift-gated (#133);
  Alembic versioned migrations (#134); DuckDB as the preprocess heavy-lift engine (#135);
  pyright on `backend/` (#136); cross-language contract fixtures (#137); Qt puller frozen
  bug-fix-only with a named Textual-TUI successor (#138). Fresh DuckDB artifacts +
  current-main image deployed to prod 2026-06-13.
- **Deployed to production (#16).** The app is live (Fly single always-on machine,
  SQLite-on-volume + Litestream→R2 backups, Cloudflare front; ADR-064). DuckDB-WASM +
  PMTiles served client-side over HTTP Range. `deploy.sh smoke` asserts unauth
  `/data/processed/*` → 401/403.
- **2026-06-06/07 — UI overhaul + Settings (PRD #103/#119/#121/#125; ADR-065/066/067/068).**
  Three-section IA (Dashboard · Explore · Leads) + Dashboard digest hub; the Tasks
  subsystem (`task` table, `/api/tasks`, Tasks page, auto follow-ups); tower-grained
  Explore + per-tower `score` (owners index → **schema v5**); inbound-reply activity
  seam (`ContactAttempt.direction`); per-user Settings (theme/colorblind/basemap/
  default view/filter defaults) + self-service password change.
- **2026-05-31/06-02 — auth (PRD #75 + #83; ADR-062/063).** Username/password front
  door replaced magic-link; teams-as-tenants; the credential source re-authorizes every
  request; identity-only JWT. (Storage later moved to the DB by #130/ADR-069.)
- **2026-05-30 — lead-centric triage redesign complete (PRD #46, ADR-061).** Slices
  #47–#53: write-layer tracer → auth → full Lead page (owners index v2) → structures-first
  map → My-Leads kanban → top-bar filters + owner/ASR search (v3) → manual owner merge/split.
- **2026-05-30 — Slice A carrier identification landed.** ULS↔ASR carrier layer
  (#11/#12/#22/#24) + carrier-list UI (#28, owners index v4 → `carriers`). Coverage
  ~6–17% of ASR towers (high-precision / low-recall) — an empty list is the common case.
- **Slice C — tunable scoring UI shipped** (#105/#114/#115; tunable live re-rank +
  named presets). Solar→parcel done (#14); billboards remain a no-op until anchor raw
  data is populated (#13).

---

## 0. 2026-05-25 pivot — pitch demo → Phase 1 product

The project reframed from "v1 pitch-quality demo across 4 states" to "Phase 1 of a fleshed-out co-founder-facing product." See [ADR-053](./adr/0053-product-phase-shift.md) and [SCOPE.md](./SCOPE.md).

**What carries forward unchanged** from the pitch-cut work:
- All v0–v3 work (data puller, preprocess framework, map app at `app/`, AR/MT remediation, schema work).
- Anchor states: AR + MT + FL + WV (NC deferred — see §4.2). WV (54) added + elevated to a committed anchor 2026-05-29 (ADR-060 — see §4.4).
- Map app v2 stack (Svelte 5 + MapLibre + PMTiles + DuckDB-WASM) — Phase 1 layers new UI on top (Slices C + D).

**What changes:**
- Audience: investor walkthrough → co-founder daily use.
- Previously hard non-goals flip to in-scope: FCC ULS carriers, billboards on parcel, solar on parcel, lease doc upload + LLM extraction, triage state / write layer, free public-records contact enrichment.
- Old "Section 6 (testing)" and "Section 7 (pitch)" of the work plan are replaced by the Phase 1 slice plan with per-slice gates.
- ADR-006 (static-site) superseded by [ADR-055](./adr/0055-hosted-private-backend.md) for write-layer features (read-only analytical layers stay static).
- ADR-010 (free-only) reframed by [ADR-057](./adr/0057-budget-posture-reframed.md) as current-budget posture (paid unlocks expected post-Phase-1).
- ADR-041 (no LLC unmasking) narrowed to paid skip-trace + shell-piercing only (free SoS officer disclosure is in scope).

---

## 1. TL;DR

**The product is live in production** and well past Phase 1's midpoint. The backend
(`backend/` — tenant-scoped FastAPI + SQLAlchemy over the cross-state owners-index
precompute `scripts/preprocess/owners_index.py`, `--owners-index`) carries Leads +
Tasks behind username/password auth; the three-section app (Dashboard · Explore ·
Leads) is the daily surface. The lead-centric redesign (PRD #46), the UI overhaul
(PRD #103/#121), Slice A (carriers), most of Slice C (tunable scoring), and the
#130–#138 hardening pass have all shipped — see **Recent milestones** above for the trail.

**Phase 1 next up:** the rest of **D+E** — lease-doc upload + LLM extraction + S3
storage (per [ADR-059](./adr/0059-llm-lease-extraction.md); **not yet started** — no
lease/extraction code on disk) — then **Slice B** (vendor inference). Slice F's
committed-anchor composes (AR + MT + FL + WV) are complete and mutually consistent:
chunked compose (ADR-051) shipped 2026-05-19, FL recomposed 2026-05-29 (county-score
gap closed, §4.1), WV added + committed 2026-05-29 (ADR-060, §4.4); `index.json` lists
05, 12, 30, 54. NC (37) stays deferred / a Phase-1 stretch (§4.2).

| State | Raw data | Normalized | Composed | Notes |
|---|---|---|---|---|
| **AR** (05) | ✅ | ✅ 2,116,976 parcels | ✅ 11 joins, 8 views, 0 warnings | Audited clean 2026-05-21. |
| **MT** (30) | ✅ all 56 counties | ✅ 920,111 parcels | ✅ 11 joins, 8 views, 0 warnings | Audited clean 2026-05-21. |
| **FL** (12) | ✅ all 67 counties (~28 GB raw intact) | ✅ 11,184,113 parcels (fdor_nal) | ✅ recomposed 2026-05-29 — 11,425,608 parcels, 11 joins, 8 views, 0 warnings | Live in app. County-score gap **closed** 2026-05-29: `county_scores` layer + tower/solar county-score joins now present; consistent with AR/MT (§4.1). |
| **WV** (54) | ✅ statewide .gdb (WVGISTC, SB 588) | ✅ 1,389,855 parcels (wv_parcels) | ✅ 11 joins, 8 views, 0 warnings | 🆕 Added 2026-05-29 (PR #44); **committed anchor** 2026-05-29 (ADR-060). Live in app. §4.4 |
| **NC** (37) | ❌ deleted 2026-05-20 | ❌ | ❌ | ⏸️ Deferred / Phase-1 stretch — re-fetch from NC OneMap (504s) + normalize + compose deferred, not a committed anchor (§4.2). |

Four committed anchors: AR + MT + FL + **WV** (WV elevated 2026-05-29 — ADR-060, §4.4). Dropped entirely from this cut: IN (18) and UT (49) — no owner data; MN (27) — license ambiguity.

---

## 2. What works

- **AR + MT + FL end-to-end** — pull → normalize → compose → 8 views. FL was re-normalized 2026-05-26 and **recomposed 2026-05-29** (11,425,608 parcels, 11 joins, county-score gap closed) and is live in the app.
- **WV (54) end-to-end** — `wv_parcels` (statewide WVGISTC `.gdb`, SB 588) → normalize (1,389,855 parcels) → compose (11 joins, 8 views, 0 warnings; joined to national towers + ARC/HUD/USDA distress) → live in the app. Added 2026-05-29 (PR #44); a **committed Phase-1 anchor** (ADR-060, §4.4).
- The v3 preprocess framework, the puller, Git + CI.
- **One annotator per parcel/infra concept** — `scripts/preprocess/annotators/` holds a single deep implementation per annotation (owner_cluster, county_score, spatial_attribute, parcel_hosts_infra, interestingness) behind a `prepare`/`annotate` seam, fed by both the streaming Composer (per shard) and the registered tower/solar Joins (whole layer), so the two feeds can't drift; the three dead whole-layer parcel twins are retired. Owner identity lives in exactly one place — `cluster.py` (`normalized_owner_cols` + the within-state `cluster_id` / national `cross_state_owner_key` grains). Merged 2026-05-30 (PR #73), AR composite byte-identical before/after.
- Map app at `app/` — Svelte 5 + MapLibre + PMTiles + DuckDB-WASM; reads catalog-driven composites for any composed state.
- **FL normalizer code** is correct and verified (geometry bug fixed; ADR-050 streaming per-county normalizer). FL re-normalized + composed successfully on 2026-05-26 via the chunked path (ADR-051); re-running `python scripts/preprocess.py --state 12` reproduces it.
- **Chunked compose** (ADR-051) — memory-bounded per-county streaming Composer; the only compose path now (single-shot retired 2026-05-27). Closed #9.
- **Solar→parcel enrichment** — `SolarToParcelJoin` combines USPVDB polygons + EIA-860 points (both normalize to the `solar_facility` type); `has_solar` / `solar_count` populated on parcels in AR/MT/FL, covered by `tests/test_infra_to_parcel.py`. Closed #14.

---

## 3. What does NOT work / is incomplete

| Item | Severity | Detail |
|---|---|---|
| NC raw data | ⏸️ Deferred | Deleted 2026-05-20. Re-fetch from NC OneMap deferred to a Phase-1 stretch (endpoint intermittently 504s). Not a committed Slice-F deliverable. §4.2 |
| NC normalize + compose | ⏸️ Deferred | Follows the deferred NC re-fetch — future stretch, not gating. |
| FCC ULS carriers (normalize + ASR join + UI) | 🟢 Merged (#11/#12/#22/#24 + UI #28 / PR #71) | ULS Cellular/PCS/AWS-700 → canonical license/location/entity (#12); ULS↔ASR asr-number + coordinate-tolerance join calibrated (#11); licensee→consumer-brand rollup (#22); the hybrid join puts a `carriers` list on every tower (#24, owners-index → **schema v4**). Carrier-list UI — confidence badges + tooltips + empty state on the LeadPage holdings + DetailsPanel tower panel — merged (#28). **Coverage ~6–17%** of ASR towers (high-precision / low-recall) — an empty list is the common case. |
| Billboards normalizer + join | 🟡 Slice C (partial) | `fdot_/ncdot_/txdot_billboards` normalizers + `BillboardToParcelJoin` are registered and emit `has_billboard`/`billboard_count`, but billboard raw isn't populated for the anchors (FL composed the join as a no-op) and there are no tests yet (#13). ADR-014 partially reverses. *(Solar join is done — see §2, #14.)* |
| Backend (FastAPI + Postgres + auth) | 🟢 Auth + Lead page + map + kanban + filters + merge/split (#47–#53) | Lead write-layer on disk: tenant-shaped `lead` (now with editable `contact_*` columns) / `contact_attempt` / `owner_cluster_override`, `LeadStore` + `OwnersIndexService` + `OwnerMergeService` + status ladder, SQLite dev / Postgres via `DATABASE_URL`. **Username/password auth** (HS256 JWT, route-level tenant-from-JWT, fail-closed `AUTH_DEV_MODE`; the tenant=`1` stub is gone — the #48 JWT seam, reworked from magic-link to a `POST /api/auth/login` front door by PRD #75 / #76–#78, ADR-062; magic-link machinery removed). **Full Lead page merged** (Slice 3, #57 — holdings + mini-map + contact + attempts + auto-logged status). **Structures-first map merged** (Slice 4, #50 / PR #58 — clustered towers across all anchors, hover preview, click → landowner Lead, parcels on-demand; consumes the static read-layer, no backend change). **My-Leads kanban merged** (Slice 5, #51 / PR #60 — drag-to-change-status worklist; adds tenant-scoped `GET /api/my-leads` + `GET /api/counts`, reusing the existing ladder-validating + auto-logging status `PUT`). **Top-bar filters + owner/ASR search merged** (Slice 6, #52 / PR #63 — one shared lead-centric `FilterModel` narrows the map's towers + the Candidates list; `OwnerSummary` + owners index gain the v3 filter rollups + a slim client `owners_filter.json`; consumes the static read-layer, no new write surface). **Manual owner merge/split shipped** (Slice 7, #53 / PR #65 — `OwnerMergeService` + `owner_cluster_override`; `display_cluster_id = coalesce(override_target, raw_cluster_id)` applied in one place in the read path; `POST /api/leads/{id}/merge` + `/split`; raw cluster ids never mutated so overrides survive a recompute). Per [ADR-055](./adr/0055-hosted-private-backend.md). S3 lease-doc storage still ⬜. |
| Cross-state owners index (Lead identity) | 🟢 Merged (#47); **schema v5**; **manual override (#53)** | `scripts/preprocess/owners_index.py` (`--owners-index`): name-anchored cross-state `display_cluster_id` + rollups (ADR-056 score); ~16,237 owners across the 4 anchors. Schema version history is owned by [`scripts/preprocess/AGENTS.md`](../scripts/preprocess/AGENTS.md): v2 holdings/mailing/tallest, v3 filter rollups + slim `owners_filter.json`, v4 `carriers`, **v5 per-tower `score`**. **Slice 7 (#53)** layers manual merge/split on top via the `owner_cluster_override` table (`coalesce(override_target, raw_cluster_id)`) without touching the static index — raw ids stay stable, so overrides survive a recompute. |
| Lease doc upload + LLM extraction | ⬜ Slice D+E | Per [ADR-059](./adr/0059-llm-lease-extraction.md). 20-lease gold-set built first. **Not started** — no lease/extraction code on disk. |
| Vendor inference | ⬜ Slice B | ASR registrant + portfolio rollup. Lowest Phase 1 priority. |
| Tests (backend + LLM eval + multi-tenancy) | 🟡 Partial | Backend `LeadStore` + multi-tenancy isolation + status-machine tests landed with the Slice 1 tracer (#47), auth tests with Slice 2 (#48) — since reworked for username/password login (PRD #75 / #76–#78), and Slice 3 (#49) added contact-CRUD / append-attempt / auto-log / holdings-rollup / migration / full-Lead-page-API tests, and Slice 5 (#51) added `list_my_leads`/`counts` + my-leads/counts-endpoint + drag-driven illegal-409 / legal-persist-and-auto-log + per-tenant board/counts tests (plus the `KANBAN_LANES` + drag-transition cases on the Vitest `LeadStatus` machine), and Slice 6 (#52) added the deep-module **`FilterModel → query` Vitest** (byte-for-byte `composeOwnerWhere`: empty=all, multi-state OR, range bounds, score threshold; `matchesOwner` behavior; SQL/predicate consistency) + `filterTowers`/`cid` tower coverage + pytest for the new resolver rollups (counties / active-tower / structure-count / structure-types) and the slim-index projection, and Slice 7 (#53) added **`OwnerMergeService` + override-aware read-path pytest** (merge → one `display_cluster_id`; split reverses; `coalesce` honored on the served index + combined rollups; overrides survive a recompute with raw ids unchanged; tenant-scoped; the target-wins / streams-concatenate reconciliation rule) + HTTP merge/split-endpoint tests + a Vitest merge/split API-call test — default SQLite, Postgres opt-in (`PILOT_TEST_DATABASE_URL` / `PILOT_TEST_TESTCONTAINERS=1`). LLM eval still ⬜. Per [TESTING.md §11](./TESTING.md). |

---

## 4. Known issues — detail

### 4.1 FL — recomposed 2026-05-29; county-score gap closed

FL was recomposed on 2026-05-29 (`composite/12/summary.json` dated 2026-05-29): 11,425,608 parcels, **11 joins applied (0 skipped)**, 8 views, pmtiles, 0 warnings. It is live in the app (`index.json` lists 05, 12, 30, 54). The raw FDOR NAL data remains at `data/raw/fdor_nal/current/` (~28 GB, all 67 counties). Composing succeeded via the **chunked compose** path (ADR-051), which keeps peak memory bounded so FL's parcels fit on the 16 GB dev machine. (The 11,425,608 composed count = `fdor_nal` canonical 11,184,113 + `fl_fgdl_parcels` ~241,518; both FL parcel sources are composed.)

**Gap closed (FL now consistent with AR/MT):** the earlier compose (2026-05-26) had **no `county_scores` catalog layer** and **skipped `CountyScoreToTowerJoin` + `CountyScoreToSolarJoin`** because it ran before the `arc_distressed` / `usda_persistent_poverty` normalizers finished, so county-score data wasn't loaded at compose time. The 2026-05-29 recompose ran with that data present: FL now carries the standalone `county_scores` layer and both county-score joins. (The recompose also surfaced and fixed a pre-existing `safe_merge` suffix-collision bug in `apply_county_score` that crashed once FL had county-score data — see the audit remediation.) To reproduce:
```bash
python scripts/preprocess.py --state 12
```

**Per-state join status (as composed):**

| Join | AR (05) | MT (30) | FL (12) |
|---|---|---|---|
| `BillboardToParcelJoin` | skipped | skipped | ran as no-op (no billboard raw → all `has_billboard=false`) |
| `CountyScoreToTowerJoin` | applied | applied | **applied** (2026-05-29) |
| `CountyScoreToSolarJoin` | applied | applied | **applied** (2026-05-29) |
| standalone `county_scores` layer | present | present | **present** (2026-05-29) |

### 4.2 NC — deferred / Phase-1 stretch (raw deleted; re-fetch deferred)

NC is **deferred to a Phase-1 stretch** — no longer a committed anchor (see [SCOPE.md §2](./SCOPE.md)). The history and a path back are preserved here for when it's picked up.

Both `data/raw/nc_onemap_parcels/` (~8.3 GB, 1,106 of 1,186 MapServer pages) and `data/raw/NC/` (~958 MB) deleted 2026-05-20.

NC OneMap's auto-fetch paginates 1,186 pages (5,000 parcels each, ~5.9M total). The previous fetch stalled at page 1,106 on a server-side HTTP 504 at deep offsets — intermittent server degradation, not a code bug. This 504 fragility is part of why the re-fetch is deferred rather than scheduled.

**If/when NC is picked up — to re-fetch:**
```bash
python -m app_puller   # use auto-fetch for nc_onemap_parcels
```
NC compose would run via the chunked path for the same memory reasons as FL.

NB: the puller's `prepare_fresh_partial()` wipes `.partial/` at start of every fetch → new fetch cannot resume from prior partial. Real resumability fix rides along with the deferred NC re-fetch.

### 4.3 Remaining stale on-disk items

- `composite/18` and `normalized/in_parcels` — IN dropped from this cut (ADR-017); safe to delete.

### 4.4 WV — committed Phase-1 anchor (added + elevated 2026-05-29)

West Virginia (54) was added 2026-05-29 (PR #44, merged to `main`) as a new parcel source, the same way AR/MT/FL are wired, and elevated to a **committed Phase-1 anchor** the same day ([ADR-060](./adr/0060-wv-committed-anchor.md)). The 2026-05-27 50-state review ranked WV **#5 of 51** (CU 9/10, 100% ARC coverage — `docs/research/review-2026-05-27/state-WV-west-virginia-briefing.md`), out-performing the original anchors on the rubric.

- **Source:** new `wv_parcels` MANUAL_ONLY puller source (WVGISTC / MapWV statewide File Geodatabase, SB 588 free bulk; ToS reviewed and permissive). Parcel = **surface** owner (split-estate is the norm in rural WV — do not conflate with mineral ownership).
- **Composed:** `composite/54` — 1,389,855 parcels, **11 joins (0 skipped), 8 views, 0 warnings**, joined to the already-present national towers (7,330) + ARC/HUD/USDA distress (159). `index.json` now lists 05, 12, 30, 54; WV renders in the app (`parcels.pmtiles` built). Reproduce: `python scripts/preprocess.py --state 54`.
- **Two WV-specific wrinkles handled in code:** (1) owner/value/land-use live in a separate `ParcelSummary` table joined on `CleanParcelID` — handled by a new opt-in `AttributeJoin` in the shared parcel driver; (2) WV's internal `CountyID` (01–55) is **not** Census FIPS — Census collates McDowell (54047) before Marion (54049) — so county resolves via an explicit verified table, not a prefix-concat. See `scripts/preprocess/normalizers/state_parcel_adapters/wv.py` + [DATA_SOURCES.md #33](./DATA_SOURCES.md).
- **Committed anchor ([ADR-060](./adr/0060-wv-committed-anchor.md)).** WV was elevated from candidate to a committed Phase-1 anchor on 2026-05-29; the committed set is now **AR + MT + FL + WV** (reflected in [SCOPE.md §2](./SCOPE.md) / [CLAUDE.md §7](../CLAUDE.md) / README / GOALS / ROADMAP). Outreach compliance (WV §46A-6F telemarketer registration; B2B carve-out for LLC-owned parcels; mail the cleanest channel) is a business-process item, not pipeline code.

---

## 5. Commit state

Section 5 + the Section 4 source rewrites + AR/MT data-quality remediation + doc updates committed once the **AR + MT audit was clean** (revised gate; the prior gate "after FL composes" was moot while FL waited on chunked compose). `data/` is git-ignored — never commit raw or composite data.

This pivot's docs (this STATUS, SCOPE, GOALS, ROADMAP rewrites + 7 new ADRs + session summary + CONTEXT additions) commit as a single set documenting the 2026-05-25 phase shift.

**2026-05-29:** the audit-remediation work (map app fixes, preprocess hardening, FL recompose, doc reconciliation, CI lint/test fixes) was merged to `main` (PR #41; the stacked refactor + cleanup branches consolidated and deleted). The issue tracker was reconciled against this: **#9** (chunked compose), **#20** (FL compose), and **#14** (solar→parcel join) closed as completed; **#10**/**#21** (NC) marked `deferred`; **#27** (Steel-in-the-Air) flagged premise-overturned → `ready-for-human`.

**2026-05-29 (WV):** `wv_parcels` — West Virginia statewide parcels — added and merged to `main` (**PR #44**). New MANUAL_ONLY puller source + normalizer adapter + shared-driver `AttributeJoin`/`mailing_addr_is_full` (additive, opt-in); `composite/54` built (1.39M parcels joined to national towers/distress). Full suite green (251 passed), ruff clean. WV was then **elevated to a committed Phase-1 anchor** ([ADR-060](./adr/0060-wv-committed-anchor.md)) — committed set is now AR + MT + FL + WV (§4.4).

---

## 6. Phase 1 slice progress

| Slice | State |
|---|---|
| **F** — Anchor composes (AR + MT + FL + WV; FL recomposed 2026-05-29, county-score gap closed). NC compose deferred. WV (54) added + committed as the 4th anchor 2026-05-29 (ADR-060, §4.4). | 🟢 Committed anchors composed — gate met; merged to `main` 2026-05-29 (closed #9 chunked compose, #20 FL compose; WV via PR #44) |
| **A** — FCC ULS carrier identification | 🟢 Data layer **merged** (#11/#12/#22/#24 → PRs #67–#70): ULS normalized (#12), ULS↔ASR join calibrated (#11), licensee→brand rollup (#22), `carriers` on every tower (#24). Carrier-list UI — confidence badges + tooltips + empty state on the LeadPage holdings + DetailsPanel — **merged** (#28 / PR #71; owners-index → schema v4). Coverage ~6–17% of ASR towers (high-precision / low-recall) — the GOALS "≥70%" bar is overtaken by measured reality; the empty state is designed to read as normal. |
| **C** — Asset enrichment + tunable scoring UI | 🟢 Tunable scoring UI **shipped** (per-tower scoring #105, tunable live re-rank #114, named presets #115); solar→parcel join done (#14). Billboards remain a registered no-op until anchor raw data is populated (#13). |
| **D + E** — Lease docs + triage state + backend | 🟡 The backend + redesigned UI **shipped** — the lead-centric redesign (#47–#53), the UI overhaul (Dashboard · Explore · Leads + Tasks, PRD #103/#119/#121/#125), auth (PRD #75/#83), and the #130–#138 hardening pass; the app is live in production. **The remaining D+E work — lease-doc upload + LLM extraction + S3 storage ([ADR-059](./adr/0059-llm-lease-extraction.md)) — is not yet started.** |
| **B** — Vendor inference | ⬜ Not started. |

Outcome bar: co-founder uses the product as his primary daily triage tool for 4 consecutive weeks (after Slice B ships). See [GOALS.md §3](./GOALS.md).

---

## 7. Outstanding decisions for the user

| Item | Notes |
|---|---|
| Chunked compose | ✅ Shipped 2026-05-19 (ADR-051). Single-shot retired 2026-05-27. |
| Steel-in-the-Air free dataset — **premise overturned 2026-05-26** | The free county-level lease-rate dataset doesn't exist (per data-source research, `docs/research/reports-2026-05-26/INDEX.md`). Slice D `lease_comp` source-of-truth needs replacement — next-best free path is REIT 10-K rent disclosures + ABS securitization filings. Paid Steel-in-the-Air tier remains the Phase 2 unlock per [ADR-057](./adr/0057-budget-posture-reframed.md). |
| libpostal vs `usaddress` for owner-clustering address normalization | Deferred owner-resolution refinement (#26) — **not** in scope for the shipped name-anchored matching, and **superseded as the day-1 fix by the manual merge/split net** (#53, shipped). Lean libpostal; fall back to `usaddress` if dep-management is painful. |
| Hosting choice | ✅ Decided — Fly.io single always-on machine + SQLite-on-volume + Litestream→R2 + Cloudflare ([ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md)); deployed (#16). |
