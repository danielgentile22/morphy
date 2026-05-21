# PULLER_UX — Design Spec for the Section 3 Overhaul

**Last updated:** 2026-05-20
**Status:** Implemented — Section 3 of the work plan is complete. This
document remains the design reference for the puller's behaviour.

This document is the design spec for the data puller upgrade. The
puller is the **single tool the user interacts with most often** to
keep the system healthy; user comment: *"data puller is going to need
a lot of work in my opinion from a functionality stand point and UI as
well to make my life easier moving forward."*

This spec is what Section 3 of `/.claude/plans/cached-wobbling-token.md`
executes against.

---

## 1. Goals for the upgrade

1. **Surface freshness clearly.** The user should never wonder
   "is my data current?" — the answer is visible at a glance per
   source.
2. **Reduce friction on MANUAL_ONLY sources.** Walk the user
   step-by-step through every manual download, with deep links and
   expected-file hints.
3. **Automate what can be automated.** Bulk refresh covers auto
   sources unattended; pauses cleanly for manual sources.
4. **Tell the user what to do next.** "What needs my attention" panel
   aggregates the actionable items so the user doesn't have to scan
   the tree.
5. **Persist state.** The puller remembers where the user left off.

---

## 2. Information architecture

### 2.1 Main window layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Pilot Data Puller                                              [-][□][×]    │
├──────────────────────────────────────────────────────────────────────────────┤
│  [Check for updates] [Pull all stale] [Pull all missing] [Refresh all stale] │
│  [Rescan disk] [Verify contents] [Preprocess…] [Cancel current pull]         │
├──────────────────────────────────────────────────────────────────────────────┤
│  ⚠ What needs my attention (3 sources)                                       │
│  • nc_onemap_parcels — endpoint failing; manual walkthrough available  [▶]   │
│  • hud_oz             — endpoint failing; manual walkthrough available [▶]   │
│  • eia_860m           — Stale (39 days; cadence 30)                    [↻]   │
├──────────────────────────────────────────────────────────────────────────────┤
│  Search: [_____________]    Filter: ☐ Show retired ☐ Show deferred           │
├──────────────────────────────────────────────────────────────────────────────┤
│  ▼ FCC                                                                       │
│    ✓ fcc_asr           Fresh (3d)   402 MB   2026-05-18    [Pull now]        │
│    ⚠ fcc_uls_cellular  Deferred     310 MB   2026-05-15    (no action)       │
│  ▼ FAA                                                                       │
│    ✓ faa_oeaaa         Fresh (4h)    79 MB   2026-05-19    [Pull now]        │
│  ▼ Distress                                                                  │
│    ✗ hud_oz            Endpoint dead    —    never         [Walk me through] │
│    ✗ hud_qct           Endpoint dead    —    never         [Walk me through] │
│    ✓ arc_distressed    Fresh (200d)   1.6 MB  2026-04-12   [Pull now]        │
│  ▼ Parcels                                                                   │
│    ✓ ar_parcels        Fresh (1d)   3.2 GB    2026-05-18   [Pull now]        │
│    ✗ nc_onemap_parcels Endpoint dead   —      never        [Walk me through] │
│    ✗ mt_cadastral      Missing         —      never        [Walk me through] │
│    ✗ ut_parcels        Missing         —      never        [Walk me through] │
├──────────────────────────────────────────────────────────────────────────────┤
│  Details: nc_onemap_parcels                                                  │
│  ──────────────────────                                                      │
│  Cadence: ~90 days                                                           │
│  Last fetched: 2025-07-15 (11 months ago)  ⚠ STALE                           │
│  Endpoint status: HTTP 500 since 2026-05-19                                  │
│  Walkthrough: 5 steps available  [Walk me through]                           │
│  License: Public-record, NC OneMap attribution required                      │
├──────────────────────────────────────────────────────────────────────────────┤
│  [████████████░░░░░░░░░░] Pulling fcc_asr: 64.3 MB / 402 MB @ 8.4 MB/s       │
├──────────────────────────────────────────────────────────────────────────────┤
│  Activity log [Filter: ▼ all | errors only | session only]                   │
│  18:42:11  fcc_asr      Fetch started                                        │
│  18:42:15  fcc_asr      Validating downloaded files                          │
│  18:43:02  fcc_asr      Promoted .partial → current                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Status badges (color + icon)

| Badge | Icon | Color | Meaning |
|---|---|---|---|
| **Fresh** | ✓ | Green | Within cadence window |
| **Due soon** | ⏳ | Yellow | Past 50 % of cadence window |
| **Stale** | ↻ | Red | Past cadence window |
| **Missing** | ✗ | Gray | Not yet pulled |
| **Endpoint dead** | ⚠ | Orange | Auto-fetch endpoint failing |
| **Manual required** | ⤓ | Blue | MANUAL_ONLY policy |
| **Needs creds** | 🔒 | Purple | CREDENTIALED policy without env vars |
| **Retired** | ⊘ | Faded | Source mothballed; no action |
| **Deferred** | … | Faded | Source in registry but not in v1 scope |

Color choices follow the Wong CB-safe palette where possible (same
basis as the map app).

---

## 3. "What needs my attention" panel

Aggregates the top of the window. Surfaces, in priority order:

1. **Endpoint-dead sources with walkthroughs available** (HUD OZ /
   QCT / NC OneMap / USDA after Section 4.1).
2. **Stale sources** (past cadence).
3. **Missing sources** for anchor states (NC, MT, FL counties).
4. **Sources past `next_recommended_check_at`** but otherwise OK.

Each item is one-click-actionable from the panel:

- Auto sources: click **↻ Refresh** → pulls in background.
- Manual sources: click **▶ Walk me through** → walkthrough modal.
- Missing sources: click **▶ Walk me through** → walkthrough modal.

The panel collapses when empty ("All sources current ✓").

---

## 4. Walkthrough modal (MANUAL_ONLY sources)

The single biggest UX improvement. Replaces today's static description
text with a guided flow.

### 4.1 Modal anatomy

```
┌─────────────────────────────────────────────────────────────────┐
│  Walk me through: nc_onemap_parcels             Step 2 of 5  × │
├─────────────────────────────────────────────────────────────────┤
│  [< Prev]                                          [Skip] [Next>]│
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Step 2: Click "Graham" on the county map                       │
│  ─────────────────────────────────────────                      │
│                                                                 │
│  On the NC OneMap "Get Parcels" page, click directly on         │
│  Graham County (in the southwestern Appalachian corner) to      │
│  select it.                                                     │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                                                          │   │
│  │       [Screenshot: NC OneMap county-picker page]         │   │
│  │                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Open in browser: https://www.nconemap.gov/datasets/...   [↗]   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Step contents

Each `ManualStep`:

- `title: str` — short, action-oriented ("Click Graham on the map").
- `body: str` — Markdown; rendered inline.
- `screenshot: Path | None` — optional, under
  `app_puller/assets/walkthroughs/<source_id>/`.
- `deep_link: str | None` — opens in OS browser.
- `expected_files: list[str] | None` — final filenames the user
  should see; checked in the post-walkthrough validate step.

### 4.3 Modal closing

- **Last step "I'm done"** → puller runs the source's
  `validate(files)` against `data/raw/<source_id>/current/`.
- **If validate passes** → promote files to `current/` (atomic
  rename), mark `local_version = "manual"`, update manifest.
- **If validate fails** → show the validate error; offer to re-open
  the walkthrough at step N.

---

## 4.5 Upload file(s) button

Manual downloads land on the user's Desktop by default. To avoid the
"navigate to `~/Projects/pilot/data/raw/<id>/current/` in Finder, drag
files in" friction, the puller exposes an **Upload file(s)** button in
two places:

1. **Details pane** — bottom-right action bar of the source detail
   panel, between Pull and Open URL. Works for every source (auto or
   manual), useful when an auto-fetch is failing and the user grabbed
   the file by hand.
2. **Walkthrough modal** — between the per-step deep-link button and
   the navigation row. Lets the user upload mid-walkthrough without
   having to leave the modal.

Both call the same helper in `app_puller/upload.py`:

- File picker opens at `~/Desktop`.
- Multiple files selectable in one go (the typical shapefile set is
  `.shp` + `.shx` + `.dbf` + `.prj`).
- ZIPs get an opt-in **Auto-extract** prompt (uses the same
  `safe_extract_zip` helper as the fetch pipeline).
- Overwrites of existing files are confirmed once at the top of the
  flow.
- Files are **copied** (not moved) — the original on Desktop is
  preserved so the user can clean up at their leisure.

After upload from the details pane, the main window's
`_detect_manual_installs()` reruns to update the manifest. From the
walkthrough modal, the existing "I'm done" finalize step picks up
whatever was uploaded.

---

## 5. Bulk refresh

Two top-bar buttons handle the routine workflow:

### 5.1 "Pull all stale" — unattended

Runs through stale auto-policy sources one at a time. Manual sources
are **skipped** with a notification at the end ("3 manual sources
remain stale: nc_onemap_parcels, hud_oz, hud_qct — open the puller to
walk through them").

Background process. Progress bar reflects current source. The user
can quit the puller; the pulls continue in a child process and the
manifest is updated atomically.

### 5.2 "Refresh all stale (with manual prompts)" — assisted

Runs through every stale source in registry order:

- Auto source → fetch in background; advance.
- Manual source → pause, open walkthrough modal; resume after the user
  closes it ("I'm done" or "Skip").
- Credentialed source missing creds → prompt to add env vars; either
  set + retry or skip.

Cancel button stops after the **current** source finishes (matches
the prior "Cancel current pull" semantics — never abort mid-fetch
since `.partial` to `current/` is atomic).

---

## 6. Pre-pitch checklist flow

New entry point: **Pre-pitch checklist** menu item.

When clicked:

1. Triggers `Check for updates` (parallel HEAD).
2. Identifies stale-but-needed sources for active anchor states (read
   from `docs/SCOPE.md` — or hardcode in registry: AR/NC/MT/UT/FL).
3. Surfaces a focused checklist:
   - [ ] AR — fresh
   - [ ] NC — STALE — refresh now (auto-fetch, MapServer pagination)
   - [ ] MT — MISSING — walkthrough
   - [ ] FL — MISSING — walkthrough (67-county FDOR NAL)
   - [ ] HUD OZ — endpoint dead — walkthrough
4. After each item completes, the row checks itself.
5. Bottom button: "Re-run preprocess for affected states" launches
   the preprocess dialog with those states preselected.

This is the muscle memory the user runs before every partner
walkthrough.

---

## 7. Persisted UI state

Stored in `~/.config/pilot/puller_state.json`:

- Last-selected source.
- Expanded categories in the tree.
- "Show retired" / "Show deferred" filter toggle states.
- Activity log filter setting.
- Window position + size.

Loaded on launch; saved on close.

---

## 8. Activity log improvements

Today's log is monolithic. After Section 3:

- **Filter dropdown**: All / Errors only / This session.
- **Per-source filter**: clicking a source in the tree filters the
  log to that source.
- **Copy-to-clipboard** button: copies the visible log for pasting
  into a bug report or diagnose prompt.
- **Diagnose-with-AI button** stays as-is (requires `ANTHROPIC_API_KEY`).

---

## 9. Behind the scenes — data model changes

| Change | Where | Section |
|---|---|---|
| `update_cadence_days: int | None` on every source | `scripts/fetch/base.py` | 3.1 |
| `manual_walkthrough() -> ManualWalkthrough` on MANUAL sources | `scripts/fetch/base.py`, each source file | 3.2 |
| `ManualWalkthrough` dataclass | `app_puller/walkthroughs.py` | 3.2 |
| `next_recommended_check_at` field on manifest | `scripts/fetch/manifest.py` | 3.1 |
| Manifest `schema_version` bump to 2 | `scripts/fetch/manifest.py` | 3.1 |
| `ManualWaitWorker` | `app_puller/workers.py` | 3.4 |
| Walkthrough screenshots committed to repo | `app_puller/assets/walkthroughs/<id>/*.png` | 3.5 |

---

## 10. What this design explicitly does **not** include

- Notifications (desktop / email / Slack) — future
- Multi-user sync — future
- Web-based puller UI — out of scope; desktop-only
- Auto-retry on transient failures — future (today: manual retry)
- Schedule-based auto-pull — explicitly rejected per ADR-005

---

## 11. Acceptance criteria (Section 3.6 verification)

The Section 3 work is **done** when:

- [ ] Puller launches; freshness column populated for every installed
      source.
- [ ] Selecting each MANUAL_ONLY anchor source (mt_cadastral_parcels,
      fdor_nal) opens a walkthrough with ≥ 3 ordered steps + deep link.
- [ ] "What needs my attention" panel lists the broken-endpoint sources.
- [ ] Bulk "Refresh all stale (with manual prompts)" runs end-to-end.
- [ ] `data/manifest.json` carries `next_recommended_check_at`.
- [ ] Activity log filter dropdown works.
- [ ] Puller state persists across launches.
