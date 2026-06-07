# UI Overhaul — Working Plan (grilling in progress)

**Status:** 🟢 Grilling complete — 13 decisions captured (§3), full phased plan in
§5. Ready to convert to a PRD / issues and implement. (ADR candidates in §8.)
**Started / converged:** 2026-06-06
**Driver:** Big information-architecture redesign of the map app — move from a
map-first app with overlay surfaces to a **Dashboard / Explore / Manage**
three-section model.

This file is written incrementally during a `/grill-with-docs` session so the
in-progress thinking survives a dropped connection. The final artifact will be a
phased implementation plan a future Claude Code session can build from.

---

## 1. The brief (verbatim, as given)

> When you open app it opens on a dashboard page. Shows things that need our
> attention like replies we received or follow ups we need to do and shit like
> that. Below that a calendar view showing all the activity on the app (last
> time we contacted anyone was 3 days ago, last reply we got was yesterday).
>
> Then two other views: **Explore** and **Manage** (or some other name).
>
> **Explore** has two possible views — map or long list — both filterable by
> whatever filter we want, and every tower/owner is ranked. Explore should be
> **tower-oriented** (you open the map to find an interesting antenna, not an
> interesting owner).
>
> **Manage** has every antenna/owner we have moved to researching or contacted.
> Manage should be **owner-oriented** (you can't call a tower, you call a human).
>
> Design the UI around **what we do**, not random pages. Dashboard = what opens
> automatically, manages/shows what needs doing and what's been done. Explore =
> browsing to find antennas. Manage = where you actually make money.
>
> Cleaner flow so we never get lost in an overcrowded part of the app. Splitting
> it this way lets each view behave differently.
>
> Dashboard combines everything + nice-to-haves: calendar, notifications, todo
> tasks (manually created or auto-created by the app). Example auto-task: set up
> automatic follow-ups 3 months after the first message for every owner that
> ignored us — app looks at towers we contacted, ignores the ones that replied,
> adds the rest to the calendar exactly 3 months from our first message.

Explicitly **out of scope for now:** fonts, colors, visual styling. This is
about flow / information architecture / behavior.

---

## 2. What exists today (codebase snapshot, 2026-06-06)

The redesign is less green-field than it looks — three of the proposed sections
map onto surfaces that already exist.

**Current navigation (`app/src/App.svelte`):** map-first. A persistent MapLibre
map is the base layer; hash routes (`#/candidates`, `#/leads`, `#/lead/:key`)
render full-screen overlays on top of it so the map never unmounts.

**Existing surfaces:**
- **Map** (`MapView.svelte`) — structures-first: clustered tower points across
  all 4 anchors (AR/MT/FL/WV). Hover previews owner·ASR·height·state. Clicking a
  tower resolves its landowner and opens that owner's Lead page. Parcels demoted
  to an on-demand high-zoom layer. A shared `TopFilterBar` + "More" popover +
  owner/ASR search narrows it.
- **Candidates** (`Candidates.svelte`) — discovery list: owners at status **New**,
  ranked by interestingness score, narrowed by the same shared `FilterModel`.
- **My Leads** (`MyLeads.svelte`) — kanban grouped by Lead status (one lane per
  status except New; Uninterested = closed lane). Drag a card to change status.
- **Lead page** (`LeadPage.svelte`) — per-landowner detail: cross-state holdings
  + per-parcel structures + mini-map, editable contact fields, contact-attempts
  log, status with auto-logged transitions, owner merge/split.

**Backend data model (`backend/app/models.py`):**
- `Lead` — `(tenant_id, display_cluster_id)`; `status`, `notes`, `contact_name/
  phone/email`, `best_channel`, `created_at`, `updated_at`.
- `ContactAttempt` — `(tenant_id, display_cluster_id)`, `occurred_on` (date),
  `channel`, `outcome`, `note`. Status transitions auto-log a row with
  `channel='status'`. **This is the only record of activity over time.**
- `OwnerClusterOverride`, `Tenant`, `User`.
- **Lead status ladder:** `New → Researching → Contacted → (Interested →
  In Business | Uninterested)`. Default New. Terminal: In Business, Uninterested.

**Key domain facts (`CONTEXT.md`):**
- The **Lead** is owner-centric and cross-state — one landowner = one Lead even
  if they own many towers in several states (you make one phone call). A tower is
  the *reason* a Lead is interesting; the Lead is *who you call*.
- A **Candidate** is just a Lead at status New (no separate saved/tracked flag).
- Carrier coverage is ~6–17% of towers — empty carrier list is normal.

**What does NOT exist today (genuinely new for this redesign):**
- No dashboard / landing page (app opens on the map).
- No **task / follow-up / reminder** entity. `ContactAttempt` records the *past*;
  nothing models a *future* scheduled action.
- No **inbound / "reply"** concept. `ContactAttempt.outcome` is free text; there
  is no structured "they replied" signal and no email integration.
- No **calendar / activity timeline** view.
- No **notifications**.
- No **automation / rule engine** (e.g. auto follow-up after N months).

**Likely-clean mapping (my working hypothesis, to be confirmed/corrected):**
| Proposed section | Maps onto today | Net-new work |
|---|---|---|
| **Explore** | Map + Candidates list, unified, filterable, ranked | Toggle map⇄list; tower-orientation |
| **Manage** | My Leads kanban (owners off New) + Lead page | Owner-orientation; naming |
| **Dashboard** | — (nothing today) | Attention feed + calendar + tasks + automation |

So the heavy net-new engineering concentrates in the **Dashboard + task/calendar/
automation subsystem**; Explore and Manage are largely a re-home + reframe of
existing surfaces.

---

## 3. Decisions log

_Appended after each grilling question is answered. Format: question → decision →
rationale / consequences._

### D1 — Explore is tower-grained in **both** views (2026-06-06)

**Decision:** In Explore, the primary object is the **tower/antenna** in both the
map and the long list. Map points = towers (as today). List rows = towers, ranked
by their owner/parcel interestingness score. Clicking a tower opens a tower-first
detail; acting on it hands the **owner** off to Manage (handoff mechanics TBD, D2).

**Rationale:** Most literal honoring of "you open the map to find an interesting
antenna, not an interesting owner." The map is already tower-grained, so making
the list match keeps Explore internally consistent — one object, two lenses.

**Consequences / open threads:**
- **Ranking is owner/parcel-derived.** Towers carry no independent score today;
  a tower's rank = its owner's score. Two towers of the same owner tie. **(Revised
  by D3 — towers now get their own score.)**
- **Prolific-owner redundancy** in the list (40 AT&T towers = 40 top rows, same
  score) — needs a resolution (collapse-by-owner? show-all? dedupe-with-count).
  → folded into the next question.
- The owner-centric **Lead** (ADR-061) is untouched as the unit of *work*; Explore
  is the discovery lens, Manage is the work surface. The tower→owner resolution
  the map already does (`towers.ts` client-side cluster key) is the bridge.

### D2 — Pursuing a tower advances the **owner** Lead; the trigger tower is recorded (2026-06-06)

**Decision:** "Pursuing" an interesting tower in Explore advances that **owner's**
Lead `New -> Researching` (today's "start tracking a candidate"), bringing **all**
the owner's towers as holdings — one owner, one Lead, one human to call. The
specific antenna that sparked it is recorded as the Lead's **trigger** and shown
as context on the Manage card / Lead page ("flagged from ASR 1287345").

**Rationale:** The handoff *is* the tower->human conversion: you browse antennas,
but the moment you act you commit to calling a person. Keeps the one-owner-one-
call model (ADR-061) intact while preserving the discovery context that's
otherwise lost ("why are we calling them? — their 300ft Pulaski tower").

**Consequences / open threads:**
- **New data:** a Lead needs to carry its **trigger** asset reference. Two cheap
  implementations: (a) a dedicated `Lead.trigger_asr` (nullable) column, or (b)
  reuse the activity log — auto-log a `channel='flag'` ContactAttempt at the
  New->Researching transition and derive the trigger from it. Decide at build
  time; (b) avoids a schema change and supports flagging more than one tower over
  time.
- Clicking a tower whose owner is **already** in Manage must show "Open in Manage"
  (not "Start researching") and optionally append another trigger. (UI detail.)
- A tower-click should also support a **read-only peek** (inspect without
  committing) distinct from the commit action.

### D3 — Towers are individually scored, each with its own detail page; owner is a link (2026-06-06)

**Decision:** Rejecting all three dedup options. Instead: **each tower carries its
own ranking/score and its own detail page.** The Explore list is a flat list of
towers, each independently scored — so same-owner towers no longer tie and the
"redundant rows" problem disappears at the root. On every tower row/page the
**owner is always clearly visible as a link**; clicking it opens the **owner page**,
which shows **all of that owner's towers, ranked and filterable**.

**Rationale (user):** "Each tower needs its own ranking, score, details, page... that
said owner should always be clearly visible and a link that opens the owner page
and shows all the towers ranked and filterable."

**Consequences / open threads:**
- **New: per-tower score.** Today interestingness is parcel-grained, rolled up to
  the owner; towers carry no score. Each tower must now get its own. Natural basis:
  the tower's **underlying parcel** interestingness (already computed parcel-grained
  — different towers sit on different parcels, so scores differ naturally),
  optionally enriched with tower-specific signals (height, # carriers, active,
  vendor). → basis is the next question. Connects to **Slice C tunable scoring**
  (ADR-058) — the weights belong there.
- **New surface: tower detail page.** Today a tower-click resolves straight to the
  owner Lead; there is no tower page. Explore now needs one (tower facts: ASR,
  height, type, carriers, active, parcel, location, score + owner link + pursue).
- **Owner page = the existing Lead page (reused).** The Lead page already renders
  cross-state holdings + per-parcel structures and already works for owners at
  status New. It becomes the "owner page" the tower's owner-link opens; it needs a
  **ranked + filterable** view of the owner's towers (today they're listed, not
  ranked/filtered). Same surface in Explore (New owner) and Manage (worked owner).
- Owners are **navigable from towers**, not a primary Explore list of their own.
  This fully settles D1 "towers everywhere": Explore's list is towers; owners are
  reached by link.

### D4 — The score is **user-customizable** with **named savable presets** (2026-06-06)

**Decision:** The tower score is not a fixed formula — it's a **customizable
weighted blend** the user configures in the UI: pick which **parameters/features**
feed the score and set their **weights**. The user can **save a configuration as a
named preset** and reuse it later (e.g. "Distressed rural", "High-value metro").
The active preset ranks the towers in Explore. **Future:** an ML model that learns
from a feature set which towers best fit our goals (explicitly out of scope now —
noted as direction).

**Rationale (user):** "A key feature is to make the score customizable... For now
just make the scoring parameters and weights customizable somewhere in the UI.
Also make it so we can save presets... save and name that set and use it again."

**This expands the planned Slice C (ADR-058 tunable transparent scoring)** with:
(1) **tower-grain** scoring (ADR-058 was parcel/owner-grained), (2) **named saved
presets**, (3) a stated **ML future**. → The plan should *extend ADR-058*, not add
a competing ADR.

**Recommended sub-decisions (confirm later if you disagree):**
- **Feature menu** (what's weightable): parcel signals already in the data —
  distress tier, OZ / QCT / persistent-poverty flags, total assessed value,
  acreage, portfolio size — plus tower signals — height, carrier count, active
  status, vendor known/unknown. Enumerated precisely in the plan against what each
  tower actually carries.
- **Default preset** = today's parcel interestingness (so nothing regresses).
- **Preset storage** = **tenant-shared** (2-person team, one tenant — both see the
  same presets). Persisted in the backend (`scoring_preset` table, tenant-scoped).
- **Owner ranking** (owner page / Manage sort) = an **aggregate** of the owner's
  tower scores under the active preset (default: their best/max tower). So one
  preset drives both tower and owner ordering.
- **Compute** = client-side over DuckDB-WASM per ADR-058 (instant re-rank on weight
  change); only the named presets persist to the backend.

**Open thread:** exact feature list + weighting UX (sliders? 0–100? on/off +
weight?) deferred to the plan.

### D5 — The owner-work section is named **"Leads"** (2026-06-06)

**Decision:** The third section is **Leads** (not Manage/Pipeline/Outreach). Scope:
every Lead **off New** (Researching / Contacted / Interested / In Business +
the closed Uninterested lane) — exactly today's **My Leads** kanban. Structure:
kanban-by-status, plus an optional **list view** (mirrors Explore's map/list
duality). Each card is **owner-grained** and shows its **trigger** tower (D2).

**Rationale (user):** "Maybe just calling it Leads is the way to go." Matches the
existing "My Leads" surface and the `Lead` domain primitive; "My Leads" → "Leads"
is a clean shortening.

**Glossary nuance (resolved, no conflict):** every owner is technically a Lead
(default status New), so the **Leads** section is the **worked subset** (off New);
the New/Candidate pool lives in **Explore** as the discovery surface. This is
already exactly how "My Leads" behaves today, so the naming carries no new
ambiguity. The standalone **Candidates** *surface* folds into Explore; "Candidate"
survives only as shorthand for "a Lead still at New."

**Three-section nav (locked):**  `Dashboard · Explore · Leads`

### D6 — A "reply" is a first-class **inbound** activity event, manual now, integration-ready (2026-06-06)

**Decision:** Model inbound replies as a first-class **event** in the existing
activity log: add a **`direction` (outbound | inbound)** to `ContactAttempt`
(default outbound). A "reply" = any **inbound** entry, **logged manually** for now
("Log reply", same flow as logging a call). The Dashboard attention feed and the
auto-follow-up rule read **inbound events**, never Gmail — so a **Gmail
integration later auto-fills the same events** with zero downstream rework.

**Rationale (user):** "Manual right now so that we have the feature. Later Gmail
integration will be the way to go but not yet."

**Consequences:**
- **Minimal schema change:** one `direction` column on `ContactAttempt`. The
  calendar/activity view is then essentially the existing attempt stream rendered
  on a timeline (past = logged events).
- **The Gmail integration becomes a pure auto-filler** of inbound events (a later
  phase) — the rest of the app is already wired to "inbound events."
- The status auto-log (`channel='status'`) stays a separate event kind; status ≠
  reply (a reply can arrive with no status change, e.g. "who is this?").
- ⚑ **Architecturally load-bearing** (the inbound-event seam decouples the whole
  Dashboard from any email provider) — candidate for an ADR when we write the plan.

### D7 — One unified, filterable **Tasks** workspace (manual-first) (2026-06-06)

**Decision:** A **single Task entity** powers **one** Tasks view — no separate
todo / follow-up / reminder surfaces. Everything lives in it and you **filter** to
find what you need. A Task covers the full range: outreach follow-ups, general
business tasks, **and internal/dev todos** ("web app development", "call with
Michael"). Key properties:
- **Links (all optional, can have both):** a Task may connect to an **owner**
  (Lead / `display_cluster_id`), a **tower** (ASR), **both**, or **neither**
  (freestanding todo).
- **Assignee:** a Task can be **assigned to a team member** (a `User` in the
  tenant) or left **unassigned**. E.g. dev work → Daniel; a lead follow-up →
  Michael or unassigned.
- **Manual-first:** for now **every** Task is **manually entered**. Automations
  (auto-created follow-ups) and Gmail come **later** — "I want to first see it work
  before connecting it to other areas of the app or Gmail."

**Rationale (user):** wants one filterable home for all task types rather than
multiple overlapping views; wants rich connectivity (owner/tower/assignee) and
told me to "add as many fields like this as we can think of."

**Proposed Task schema (to confirm — next question):**
`id, tenant_id, title, description, status, priority, due_date, assignee_user_id?,
created_by_user_id, lead_cluster_id?, tower_asr?, category/labels, source
(manual|auto), created_at, updated_at, completed_at`.
**Filterable by:** assignee, status, due window (overdue / today / week), linked
owner, linked tower, category, priority, source.

**Consequences:**
- **Surfaces team members.** Assignment needs the tenant roster (the `User` table
  exists; may want a display **name** per user — today `User` stores email only).
- Owner/tower-linked tasks also surface on that owner's Lead page / the tower page.
- This is the **first build target** of the Dashboard subsystem (standalone,
  manual). The attention feed, calendar, automations, and Gmail all build *on top*
  of Tasks + inbound events once those manual primitives are proven.

**⚑ PHASING SIGNAL (load-bearing for §5):** build the **manual primitives first**
(Tasks + inbound reply events + their views), prove them, **then** layer
automation, **then** Gmail. The user explicitly wants to see the manual version
working before wiring cross-app automation.

### D8 — Task schema locked; **every field filterable + free-text search** (2026-06-06)

**Decision:** The Task schema from the question is accepted:
`id, tenant_id, title, description, status (Open|In Progress|Done), priority
(None|Low|Med|High), due_date?, assignee_user_id?, created_by_user_id,
lead_cluster_id?, tower_asr?, labels (free-form, optional), source (Manual|Auto),
created_at, updated_at, completed_at`.

**Filtering (the emphasis):** the Tasks view must let you filter by **any** field
— assignee, status, priority, due window, **lead**, **tower**, source, label —
**plus a free-text search box** that matches the typed words against **title and
description** (substring/contains). Categories are **free-form labels** (not a
rigid enum), themselves a filterable field.

**Rationale (user):** "Filter for any one of the fields listed above... add title
and description filtering too where I can type in an empty text field and it finds
all titles or descriptions that contain the words I typed."

**Build note:** mirror the existing shared **`FilterModel`** pattern
(`app/src/lib/filter-model.ts`) — a field registry that yields both a predicate and
(if tasks are queried server-side) a query, so the filter set stays one source of
truth. Free-text is a `title/description ILIKE %word%` (or client substring).

### D9 — Dashboard is a **digest hub with expandable sub-pages**; top-nav stays the big 3 (2026-06-06)

**Decision:** Top-level navigation is exactly **three** sections — **Dashboard ·
Explore · Leads**. **Tasks is NOT a top-level page.** Instead the **Dashboard** is a
**hub of digests**, each expandable to a full **sub-page**:

| Dashboard digest (quick view) | Expands to sub-page | Full sub-page shows |
|---|---|---|
| **Attention** — replies to handle + needs-attention items | (inline / its own) | the things requiring action (see D10) |
| **Tasks** — due **today + tomorrow** + all **high-priority** | **Tasks** | the full filterable Tasks workspace (D7/D8) |
| **Calendar** — small recent/upcoming view | **Calendar** | full calendar grid of all activity + due tasks |
| **History** — recent activity | **History** | everything done in the past (full activity log) |
| **Stats** — key metrics | **Stats** | outreach #s, % replied vs not, % leads→clients, … |

**Rationale (user):** "I don't want tasks as a whole separate page — make it a
sub-page of Dashboard. I might want more sub-pages: full calendar, a full history
sub-page, a stats sub-page... Dashboard should be a quick view of all these things
with a possibility to expand any one view. The big 3 pages at the top should be
Dashboard, Explore, Leads."

**Consequences:**
- **Routing:** sub-pages are children of Dashboard (e.g. `#/dashboard/tasks`,
  `/calendar`, `/history`, `/stats`). The Dashboard landing is the digest grid.
- **Tasks digest rule (specified):** due **today or tomorrow**, **plus** any
  **high-priority** task, regardless of date. Links to the full Tasks sub-page.
- **Calendar vs History** are two lenses on the same data (Activity stream + Task
  due-dates + status changes): Calendar = time-grid (month/week); History =
  chronological feed/list. (Mirrors Explore's map/list duality.)
- **Stats is a new analytics surface** — derived from Leads + Activity (no new
  write data). Metric set pinned in D11.
- Each digest is **read-mostly**; deep interaction happens on the sub-page.

### D10 — Attention feed = unhandled replies + overdue tasks; the feed *is* notifications (2026-06-06)

**Decision:** The Dashboard **Attention** feed contains **unhandled inbound
replies** + **overdue tasks** (assigned to me or unassigned). An item **clears**
when you act on it (log a touch, create/complete a task, change status) or
explicitly **dismiss** it. **"Notifications" is not a separate system** — it's this
same feed, surfaced as a **nav badge count**. No toast/push machinery in this cut.

**Rationale (user):** selected "Replies + overdue, feed = notifications." Deferred
the stale-lead heuristic (it's really the automation rule — D12).

**Clearing mechanic (recommended):** a reply "needs attention" until there's a
**newer activity** on that Lead after the reply (a logged touch, a created/linked
task, or a status change) — derivable from the Activity stream, no new field — with
an explicit **Dismiss** as an override. Overdue tasks clear on **Done** or reschedule.

### D11 — Stats sub-page: comprehensive with breakdowns (2026-06-06)

**Decision:** The **Stats** sub-page is comprehensive: **funnel** counts at each
status; **conversion rates** between stages; **reply rate** (% of contacted who
replied); **win rate** (% → In Business); **outreach volume** over time (touches by
channel); **activity pace**. **Filterable by date range** and **broken down by team
member and by state.** All **derived** from Leads + Activity — no new write data.

**Deferred:** **asset-level conversion analytics** (which distress tier / carrier /
height / owner-kind correlate with replies & wins). Noted as a **future feeder for
the scoring presets / ML** (D4) — not in the first Stats cut.

### D12 — Auto follow-ups: **schedule-forward, cancel-on-reply** (later phase) (2026-06-06)

**Decision:** Auto follow-ups are generated **eagerly**: logging the **first
outbound touch** (or moving a Lead to **Contacted**) immediately creates a
**follow-up Task** (`source=auto`, owner-linked, `due = anchor + window`). If an
**inbound reply** is logged before the due date, the task **auto-cancels**. No
background scheduler. The auto-task is a **real, editable Task** (reassign / snooze /
label) that flows into the unified Tasks list, calendar, and Attention feed.

**Rule parameters:**
- **Anchor** = first outbound touch / status→Contacted.
- **Window** = default **3 months**, **configurable** (a Settings value).
- **Condition** = no inbound reply since anchor; lead still awaiting (status
  Contacted, not Interested/Uninterested/In Business).
- **Recurrence** (recommended): default **one-shot**; optional "repeat every N until
  status changes" as a later toggle.
- **Configurability:** ship as **one rule** with on/off + window; **architect for
  more rules later** (don't build a full rule engine in the first automation cut).

**Rationale (user):** selected "Schedule-forward, cancel on reply" — fits "see it
work," needs no infra, and keeps follow-ups as first-class editable Tasks.

**Phase:** this is a **later (automation) phase** — it presupposes the manual Tasks
+ inbound-reply primitives exist first (D6, D7).

### D13 — Build order: six phases, manual-first (2026-06-06)

**Decision (confirmed as proposed):**
1. **Shell + Explore tower-orientation**
2. **Manual primitives — Tasks + Replies + Attention** ("see it work")
3. **Dashboard views — Calendar + History + Stats**
4. **Customizable scoring + named presets** (extends Slice C / ADR-058)
5. **Automation — schedule-forward auto follow-ups**
6. **Gmail integration** (auto-fills inbound reply events)

Each phase ships something usable on its own. Detail in §5.

---

## 4. Open questions — all resolved ✅

| # | Question | Resolved by |
|---|---|---|
| 1 | Explore object: tower vs owner + handoff | D1, D2, D3 |
| 2 | Leads (Manage) name / scope / structure | D5 |
| 3 | Dashboard attention items | D10 |
| 4 | Task / follow-up entity | D7, D8 |
| 5 | Reply / inbound modeling | D6 |
| 6 | Auto follow-up rule | D12 |
| 7 | Calendar / activity view | D9 (sub-page) + §5 P3 |
| 8 | Notifications | D10 (= Attention feed) |
| 9 | Phasing | D13 |
| + | Per-tower scoring + customization/presets | D3, D4 |
| + | Dashboard IA (digest hub + sub-pages) | D9 |
| + | Stats scope | D11 |

Remaining items are **build details** (carried in §5), not open product decisions:
team-member display names for assignment; Settings location (automation window,
scoring presets); Calendar/History interaction specifics; trigger-capture
implementation (column vs activity log); fate of the current map sidebar controls.

---

## 5. Phased implementation plan

> Build target for a future Claude Code session. Respect the global invariants in
> §6 throughout (tenant scoping, schema-completeness contract, one shared filter
> model, EPSG:4326, etc.). Each phase is independently shippable.

### Phase 1 — Shell + Explore tower-orientation

**Goal:** Replace the map-first + overlay shell with the three-section app
(`Dashboard · Explore · Leads`) and make Explore genuinely tower-oriented.

**Frontend:**
- Top-level nav shell with three sections + sub-route scaffold under Dashboard
  (`#/dashboard`, `/dashboard/tasks|calendar|history|stats`, `#/explore`,
  `#/leads`). Replace the current overlay-on-map routing in `App.svelte`.
- **Explore = map + list, both tower-grained** (D1):
  - Map: keep the structures-first clustered tower layer (`MapView.svelte`),
    narrowed by the shared `FilterModel`.
  - List: new ranked **tower** list (rows = towers, each its own score), reusing
    the shared filter set; owner shown as a **link** on every row.
  - **Tower detail page** (new surface, D3): ASR, height, type, carriers
    (`CarrierList.svelte`), active, parcel facts, location/mini-map, **score**,
    **owner link**, and the **Pursue** action.
  - Owner link → the **owner page = the existing `LeadPage`** (works for New
    owners), enhanced to show the owner's towers **ranked + filterable** (D3).
- **Leads** (D5): rename `MyLeads` → Leads; keep the kanban, add a **list view**
  toggle; show each Lead's **trigger** tower on the card.
- **Pursue** (D2): advances the owner Lead `New → Researching` and records the
  **trigger** tower.

**Backend / data:**
- **Per-tower score** (D3): ensure each tower carries its **parcel's
  interestingness** score (project parcel score onto the tower in the owners/tower
  index; bump owners-index schema version with a safe default per §6).
- **Trigger capture** (D2): either a nullable `Lead.trigger_asr` column **or** an
  auto-logged `channel='flag'` activity row at the New→Researching transition
  (prefer the latter — no schema change, supports multiple triggers).

**Done when:** you can browse towers (map + ranked list), open a tower's detail,
jump to its owner's page (all their towers ranked/filterable), pursue a tower, and
see that owner appear in **Leads** with the trigger noted — all behind the new
three-section nav.

### Phase 2 — Manual primitives: Tasks + Replies + Attention

**Goal:** The manual Tasks workspace + inbound replies + the Dashboard Attention/
Tasks digests. The "see it work" phase.

**Backend:**
- **`Task` table** (tenant-scoped, D8): `id, tenant_id, title, description, status
  (open|in_progress|done), priority (none|low|med|high), due_date?,
  assignee_user_id?, created_by_user_id, lead_cluster_id?, tower_asr?, labels,
  source (manual|auto), created_at, updated_at, completed_at`. CRUD routes +
  list/filter route (filter by any field + free-text title/description search).
- **`direction` (outbound|inbound) on `ContactAttempt`** (D6); a **Log reply**
  endpoint/flow (inbound activity).
- **Team roster** for assignment: expose tenant `User`s; add a display **name**
  per user (today email-only).

**Frontend:**
- **Tasks sub-page** (D7/D8): full filterable workspace — filter bar over every
  field + free-text search, create/edit/assign/link, owner/tower links resolve to
  their pages. Reuse the `FilterModel` pattern.
- **Log reply** on the Lead page (inbound activity entry).
- **Dashboard digests** (D9/D10): **Attention** feed (unhandled replies + overdue
  tasks, clears on action/dismiss, **nav badge count**) + **Tasks digest** (due
  today/tomorrow + high-priority) linking to the Tasks sub-page.
- Owner/tower-linked tasks also surface on the Lead page / tower detail page.

**Done when:** you can create/assign/link/filter tasks in one view, log an inbound
reply, and the Dashboard shows replies-to-handle + overdue tasks (badge) and the
due/high-priority task digest — all manual.

### Phase 3 — Dashboard views: Calendar + History + Stats

**Goal:** The remaining Dashboard sub-pages, all **derived** from existing data
(Activity stream + Tasks + Lead statuses) — no new write data.

- **Calendar** sub-page + digest: time-grid (month/week) of **Activity events** +
  **task due-dates**; click a day → that day's activity; (optional) create a task
  on a day / drag to reschedule. Digest = compact recent/upcoming.
- **History** sub-page + digest: chronological feed of everything done (the full
  Activity stream incl. status changes), filterable by lead/member/channel.
- **Stats** sub-page + digest (D11): funnel, conversion rates, reply rate, win
  rate, outreach volume by channel, activity pace — **filterable by date range,
  broken down by team member + state**.

**Done when:** each digest expands to a working full sub-page; the numbers
reconcile with the underlying leads/activity.

### Phase 4 — Customizable scoring + named presets

**Goal:** Make the tower score user-tunable with saved presets (D4; extends Slice
C / **ADR-058**).

- **Scoring UI**: weight a defined **feature menu** (parcel signals: distress tier,
  OZ/QCT/persistent-poverty, assessed value, acreage, portfolio size; tower
  signals: height, carrier count, active, vendor known). Live re-rank client-side
  over DuckDB-WASM.
- **Named presets**: tenant-shared `scoring_preset` table (name + weight config);
  save / name / load / set-default. Default preset = today's parcel
  interestingness (no regression).
- **Owner ranking** = aggregate (default max) of the owner's tower scores under the
  active preset.
- **Future (out of scope):** ML-learned weights; asset-level conversion analytics
  (D11) as a feeder.

**Done when:** you can set weights, save a named preset, switch presets, and watch
Explore (and the owner page's tower list) re-rank.

### Phase 5 — Automation: schedule-forward auto follow-ups

**Goal:** The 3-month no-reply follow-up rule (D12).

- On **first outbound touch / status→Contacted**, eagerly create a `source=auto`
  follow-up **Task** due at `anchor + window`.
- On an **inbound reply**, auto-cancel the open auto follow-up for that lead.
- **Settings**: window (default 3 months), rule on/off; (later) repeat-until-status.
- Architect for additional rules without a full engine.

**Done when:** logging a first touch creates a dated follow-up task; logging a reply
cancels it; an un-replied lead's task goes overdue into Attention.

### Phase 6 — Gmail integration

**Goal:** Auto-fill **inbound reply events** from the team inbox (D6) — the rest of
the app already reads inbound events, so this is a pure auto-filler.

- Gmail OAuth; match incoming mail to leads by `contact_email`; create inbound
  Activity events automatically (feeding Attention + the cancel-on-reply rule).
- Keep manual reply logging for non-email channels.

**Done when:** an email reply from a known lead appears as an inbound event with no
manual logging, and cancels its auto follow-up.

---

## 6. Global invariants the build must respect

(From `CLAUDE.md §8`, `backend/AGENTS.md`, `app/AGENTS.md` — these don't change.)

- **`tenant_id` everywhere.** Every new table (`task`, `scoring_preset`) carries it;
  every route filters by it. Teams = tenants; auth resolves the tenant per-request
  from `users.txt` (don't reintroduce JWT tenant claims or the `tenant_id=1` stub).
- **Owners-index schema versioning.** Per-tower score (P1) extends the index — bump
  `OWNERS_INDEX_SCHEMA_VERSION`, give new fields safe defaults (a stale index must
  still serve), and **declare any new `Structure`/`OwnerSummary` field on the
  backend model** or `response_model` silently drops it.
- **Schema-completeness contract.** New surfaced composite fields go in `schema.ts`
  (+ `TOWER_SCHEMA`) first or `tests/unit/schema-completeness.test.ts` fails CI.
- **One shared filter model.** Task filtering + Explore filtering reuse the
  `FilterModel` registry pattern (`app/src/lib/filter-model.ts`) — don't fork
  per-surface filtering.
- **Don't fork owner resolution.** `display_cluster_id = coalesce(override_target,
  raw_cluster_id)` stays resolved in one place; merge/split overrides untouched.
- **Map persistence.** The MapLibre instance persists across routes today; keep it
  mounted while in Explore (don't tear it down on every nav).
- **CI gates on ruff** (`ruff check .` + `ruff format --check .`); the "placeholder"
  pytest job runs the full suite — new backend code needs tests + must stay green.

## 7. New / changed data model (summary)

| Object | Change | Phase |
|---|---|---|
| `ContactAttempt` | **+ `direction`** (outbound\|inbound); inbound = a **Reply** | P2 |
| `Lead` | **trigger** tower reference (column *or* `channel='flag'` activity row) | P1 |
| owners/tower index | **per-tower score** (parcel score projected) + schema bump | P1 |
| `Task` (new table) | unified work item — see D8 schema; tenant-scoped | P2 |
| `User` | **+ display name** (for assignment) | P2 |
| `scoring_preset` (new table) | named weight configs, tenant-shared | P4 |
| Settings (automation window, rule on/off) | new tenant config | P5 |

No changes to the static read-layer pipeline except the per-tower score (P1) and
(later) optional asset-analytics aggregates (deferred).

## 8. ADR candidates + next steps

**ADR candidates** (offered — hard-to-reverse, surprising, real trade-offs):
1. **Three-section IA + Dashboard digest-hub** — replaces the map-first/overlay
   model; shapes the whole frontend. *(D1/D5/D9.)*
2. **Inbound activity events as the provider-agnostic reply seam** — manual now,
   Gmail later, app reads "inbound events" not Gmail. *(D6.)*
3. **Tower-grained Explore with per-tower scoring; owner stays the unit of work** —
   reframes the structures-first/owner-centric tension; extends **ADR-061**. *(D1/D3.)*
- Customizable scoring + presets is better recorded as an **amendment to ADR-058**
  than a new ADR.

**Other next steps:**
- Convert this plan to a **PRD** (`/to-prd`) and/or **issues** (`/to-issues`) for
  tracked execution.
- Confirm the deferred build details in §4 when each phase starts.
