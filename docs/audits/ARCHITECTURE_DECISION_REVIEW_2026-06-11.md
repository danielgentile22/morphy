# Architecture Decision Review — 2026-06-11

A first-principles review of every significant technology and architecture
decision in this repo. **Deliberately ignores all ADRs and prior docs** — every
choice was re-derived from the code itself and judged against alternatives as
if being chosen today.

Evaluation lens (stated up front, because every verdict depends on it):

- **Team:** 2 people; one builder working with coding agents; the co-founder is
  the *user*, not a developer. No hiring planned. "Ecosystem hiring pool" is
  worth zero; "solo-maintainer leverage + AI-assistability" is worth a lot.
- **Scale:** ~15 GB raw data, ~11 M parcels in the largest state, single-digit
  concurrent users, 1 GB production VM. Write volume is two humans clicking.
- **Risk profile:** the data is parcel-owner PII compiled from public sources;
  the product treats it as private (no-store everywhere). Lead state is the
  only irreplaceable data — everything else can be recomputed from raw.

Verdict legend: **KEEP** (endorsed as-is) · **KEEP\*** (endorsed with a named
watch-trigger) · **FIX** (change, with chosen target) · **DECIDE** (genuine
judgment call surfaced to the humans).

---

## Priority table (the "what to change" answer)

| # | Decision | Verdict | Urgency |
|---|----------|---------|---------|
| 19 | `/data/processed/*` served with **no auth** (verified live in prod) | **FIX** — Caddy `forward_auth` + httpOnly session cookie | **Now** |
| 16b | JWT in localStorage | **FIX** — httpOnly cookie (same change as #19) | Now (bundled) |
| 16a | `users.txt` is the only un-backed-up state | **FIX** — back it up now; move credentials into the DB as the structural fix | Now (cheap) / soon (structural) |
| 26 | Frontend completely ungated in CI | **FIX** — add svelte-check + vitest job | Soon (an afternoon) |
| 25 | No Python lockfile (`>=` pins) | **FIX** — adopt `uv` + `uv.lock` | Soon (an afternoon) |
| 24 | `sys.path` hacks instead of packaging | **FIX** — real `[project]` table + editable install | Soon (bundles with #25) |
| 14 | Hand-duplicated API types in TS | **FIX** — generate types from FastAPI's OpenAPI | Soon (small) |
| 13 | Homegrown additive migrations | **FIX** — Alembic, triggered by the first non-additive change | On trigger |
| 2 | pandas/geopandas + hand-rolled shard streaming | **FIX (incremental)** — DuckDB for the heavy compose paths | Next pipeline work |
| 27 | No Python type checking | **FIX** — pyright on `backend/` only | When convenient |
| 23 | 2,900-LOC zero-test Qt desktop puller | **DECIDE** — freeze vs. replace with TUI/CLI | Policy decision |
| 29 | Domain logic duplicated across Python/TS | **FIX (cheap)** — shared-fixture parity test | When convenient |
| 31 | Owners index as in-memory JSON | **KEEP\*** — watch trigger ~100 MB index | Watch |
| 15 | SQLite in prod | **KEEP\*** — Postgres trigger = 2nd machine / write concurrency | Watch |

Everything not in this table was audited and **endorsed** — see the full
walkthrough below. Notably endorsed: Python, Svelte 5, Vite-without-SvelteKit,
MapLibre, PMTiles + tippecanoe, GeoParquet, the DuckDB-WASM client-side query
architecture, FastAPI, SQLAlchemy, SQLite + Litestream, the file-as-authority
auth *model*, tenant_id multi-tenancy, Fly.io + Caddy + supervisord, plain CSS
+ tokens, runes-based state, PBKDF2, and the overall test posture.

---

# Part 1 — Languages

## 1. Python for data engineering — KEEP

**Why it was picked:** the entire open geospatial ecosystem lives in Python;
fastest iteration for a solo builder; the best-supported language for coding
agents.

**Advantages:** geopandas/shapely/pyproj/pyarrow are the de facto standard for
exactly this workload (read ESRI GDB/shapefile/GPKG, clean geometry,
reproject, write parquet). One language across pipeline, backend, and puller.
Enormous LLM fluency. Every data format in this project has a mature reader.

**Disadvantages:** slow for CPU-bound row-wise work; memory-hungry (the
hand-rolled shard streaming in the composer exists *because* of this — see
§2); no compile-time type safety (see §27).

**Alternatives ranked:**

1. **Python (chosen)** — wins on ecosystem fit and iteration speed; its
   weaknesses are addressable in-place (§2, §27).
2. **Rust** — 10–50× faster on CPU-bound paths, tiny memory footprint,
   fearless refactoring. But the geo ecosystem (`geo`, `geozero`,
   `geoarrow-rs`) still has no first-class ESRI GDB reader or
   geopandas-equivalent workflow; every normalizer would triple in effort.
   Right answer for a data *product* company at 100× this scale, wrong for a
   2-person pipeline that runs monthly.
3. **Java/Scala (GeoTools, Spark/Sedona)** — the only stack with comparably
   deep geo support; built for distributed scale this project will never have.
   Verbosity and JVM ops overhead buy nothing here.
4. **Go** — great for services, near-empty dataframe/geo ecosystem. Would mean
   hand-writing format readers.
5. **R (sf)** — genuinely excellent spatial analysis, but poor for building
   maintained pipelines/services, and much weaker agent-assisted engineering.
6. **SQL-only (dbt)** — cannot ingest GDB/shapefiles or do shapely-grade
   geometry repair; would still need Python at the edges. (DuckDB *inside*
   Python is a different, good idea — §2.)

## 2. pandas/geopandas as the processing engine — FIX (incremental DuckDB adoption)

**What exists:** normalizers and the composer run on pandas/geopandas, with a
substantial hand-built streaming-shard system (bounded-memory composition,
per-chunk join adapters, streaming view aggregators, vectorized-bbox and
hoisted-rollup optimizations) so 11 M FL parcels fit in 16 GB.

**Why it was picked:** the default choice; geopandas is what everyone reaches
for; the streaming machinery was added later when memory hit the wall.

**Advantages:** works today, is well-tested, shapely under the hood handles
real-world dirty geometry.

**Disadvantages:** single-core, memory-bound, and the streaming-shard
framework is the most intricate code in the repo — bespoke machinery that
exists only to compensate for the engine. Every new state pays the memory tax.
Every join/view written against the chunked protocol is harder to reason about
than a plain query.

**Alternatives ranked:**

1. **DuckDB inside the existing framework (recommended)** — out-of-core,
   multi-core, predicate-pushdown parquet scans natively; the spatial
   extension covers point-in-polygon and bbox joins. The composer's heavy
   inner loops (infra-to-parcel aggregation, county rollups, owner clustering,
   the slim-parquet/facets steps) become single SQL statements over the
   sharded parquet — much of the streaming machinery becomes deletable.
   Keep geopandas where shapely is genuinely needed (normalize-time geometry
   repair, reprojection). This is an incremental migration, not a rewrite:
   the Normalizer/Join/View framework, manifest, and outputs all stay.
2. **Status quo** — legitimate. It works and is tested. The cost is ongoing:
   complexity in every new join/view, and compose wall-time.
3. **Polars** — multicore + streaming for tabular work, but the spatial story
   (geopolars) is stalled; you'd keep geopandas for all spatial joins, gaining
   little.
4. **PostGIS** — the most powerful spatial SQL there is, but turns a
   batch-local pipeline into a database-ops problem (load 11 M rows in, index,
   query, export out).
5. **Dask / Spark** — distributed answers to a single-machine question.

## 3. TypeScript (strict) for the frontend — KEEP

Strict mode, `noUnusedLocals`, `verbatimModuleSyntax` — already the right
configuration. Plain JS would save nothing and cost refactoring safety; no
other compile-to-JS language (ReScript, Elm) justifies its ecosystem isolation
here. Nothing to change.

---

# Part 2 — Data pipeline architecture

## 4. Homegrown ETL framework (Normalizer/Join/View/Compose, registries, manifest) — KEEP

**Why picked:** grown organically; no off-the-shelf tool fits "ingest 21
heterogeneous government sources, join spatially, emit app assets."

**Advantages:** the registry pattern (15 normalizers, 4 joins, 8 views, one
`@register_*` decorator each) is exactly the shape coding agents extend
reliably; manifest-driven freshness gives incremental rebuilds for free;
REQUIRED/AUXILIARY severity is a sensible failure policy; quality reports and
JSON-schema'd artifacts are real engineering.

**Disadvantages:** it's ~17 K LOC that only this team understands; no UI for
runs (the puller dialog covers it); orchestration is serial.

**Alternatives ranked:**

1. **Keep (chosen)** — the framework is the right altitude. Its weak layer is
   the *engine* underneath (§2), not the abstractions.
2. **Snakemake** — honest middle option: declarative DAG + file-based
   incrementality matches this workload. But the manifest already does
   incrementality, and Snakemake would orchestrate *around* the Python
   framework, adding a layer without removing one.
3. **Dagster / Prefect** — their value is scheduling, observability, and
   multi-team asset graphs. A monthly, manually-triggered, single-machine
   pipeline uses none of that; both add a daemon + UI + version churn.
4. **dbt** — SQL-transform-only; can't ingest GDB/shapefiles or run shapely.
   Could become attractive *after* a DuckDB migration (§2) for the tabular
   tail of the pipeline, but is not a framework replacement.
5. **Plain ad-hoc scripts** — what this framework rescued the project from.

## 5. GeoParquet canonical + conditional GeoJSON dual-write — KEEP

Parquet is the only format that serves both the analytics path (pyarrow,
DuckDB-WASM range reads) and archival fidelity; the row-count-tiered GeoJSON
(full < 100 K, simplified < 250 K, none above) is sane policy for the browser.
**Alternatives:** FlatGeobuf (streaming + spatial index — better for direct
browser feature rendering, worse for columnar analytics; the PMTiles layer
already covers rendering); GeoPackage (random access, but SQLite-based row
storage scans poorly); shapefile (legacy, field-name limits). No change.

## 6. tippecanoe → PMTiles static tiles — KEEP (one of the strongest choices in the repo)

Static, pre-generated vector tiles served by byte range from a plain file
server: zero tile-server ops, zero per-request compute, CDN-friendly,
perfectly matched to batch-updated data. **Alternatives:** PostGIS + martin
(dynamic tiles for live data — this data updates monthly, so paying a
stateful service for freshness nobody needs); planetiler (OSM-shaped, Java);
hosted Mapbox tiling (cost + lock-in). The only wart is the external-binary
dependency on tippecanoe, already handled with a skip-marked test. No change.

## 7. Fetch framework (DataSource ABC, AutomationPolicy, manifest, atomic writes) — KEEP

Right-sized: polite UA, streaming chunks, retry backoff, `.partial` + rename
atomicity, per-source version probes. The legal-posture enum
(ALLOWED/TOLERATED/MANUAL_ONLY/CREDENTIALED) encoded *in the type system* is
better than any off-the-shelf scraper framework would give. `httpx`/`tenacity`
would be marginally nicer than hand-rolled requests+backoff but migrating
gains nothing measurable. No change.

---

# Part 3 — Frontend

## 8. Svelte 5 (runes) — KEEP

**Why picked:** smallest runtime, best performance ergonomics, modern
reactivity; chosen at a time when the app was a lightweight map viewer.

**Advantages:** tiny bundles (entry chunk ~51 KB gz after manual chunking);
runes give fine-grained reactivity without selector/memo ceremony; scoped
styles built in; the 26-component codebase is idiomatic and consistent.

**Disadvantages:** smallest ecosystem of the big frameworks; fewer drop-in
components; historically less LLM training data than React (much less true of
current models than it was); if the team ever grew, React hires are easier —
worth zero under the stated lens.

**Alternatives ranked:**

1. **Svelte 5 (chosen)** — and note the hard parts of this app (MapLibre,
   DuckDB-WASM, PMTiles) are framework-agnostic libraries; no framework
   ecosystem helps with them. Switching would rewrite 18 K LOC to gain a
   component library the app no longer needs (it's already built).
2. **React** — wins ecosystem (react-map-gl, shadcn, TanStack) and agent
   fluency; loses on runtime weight and boilerplate. The right default for a
   team that doesn't exist yet; not worth a rewrite for this one.
3. **SolidJS** — same fine-grained reactivity idea, even smaller community
   than Svelte; strictly dominated here.
4. **Vue 3** — capable middle ground with no specific advantage for this app.
5. **Vanilla TS** — viable for pure map apps; the dashboard/leads/tasks UI
   half of this product would mean hand-rolling reactivity.

## 9. Plain Vite SPA — no SvelteKit — KEEP

SvelteKit's value is SSR, file-based routing, form actions, and edge deploy.
This app is auth-gated (no SEO), data-private (no public pre-render), and
keeps a persistent MapLibre instance alive across navigation — a requirement
that actively *fights* router-driven component lifecycles. The 120-LOC
homegrown hash router is right-sized; a router library would be more code to
configure than it replaces. **Optional cosmetic refinement:** Caddy already
has `try_files` history fallback, so switching hash routes (`#/leads`) to path
routes (`/leads`) is possible whenever URLs start getting shared around; zero
urgency.

## 10. Browser-side query engine: DuckDB-WASM over range-requested parquet — KEEP (the architecture), with two notes

**The boldest bet in the repo, and it's a good one.** Filtering/searching 11 M
parcel attributes happens *on the client* via SQL over HTTP range requests;
the server only serves bytes. This is why a 1 GB shared VM is enough.

**Advantages:** zero per-query server cost; filter latency is client-local;
offline-ish robustness; the static data tree is trivially syncable (rclone).

**Disadvantages:** heavy initial payload (the DuckDB-WASM chunk is the largest
asset; mitigated by immutable-cache chunking); client RAM/CPU on weak
machines (fine for two known users on laptops); **filter semantics live in
two engines** — SQL (parcels via DuckDB) and JS predicates (owners via the
filter index) — a real divergence risk, handled today by discipline (§29).

**Alternatives ranked:**

1. **Keep (chosen)** — at this scale, strictly dominant on ops and cost.
2. **Server-side query API** (FastAPI + DuckDB server-side) — single source
   of filter truth, thin client, works on weak devices; but every keystroke
   round-trips, and the 1 GB VM becomes the query engine for all users. The
   right move only if client diversity grows (tablets/phones).
3. **PostGIS + dynamic everything** — the "standard" answer; maximum ops for
   a dataset that changes monthly.

**Note 19 (critical, separate):** this architecture's static tree is currently
served *unauthenticated* — see §19.

## 11. State management: rune singleton classes — KEEP

Nine store classes (`AppStore`, `FilterModelStore`, …) with `$state` fields,
sync mutations, async loaders, exported as singletons. Idiomatic Svelte 5;
exactly what Redux/Zustand/XState would offer, minus the dependency. The only
watch-item: singletons make component tests share state — acceptable at
current test posture. No change.

## 12. Plain CSS + design tokens (no Tailwind, no component lib) — KEEP

Global tokens + scoped component styles + dark/colorblind themes via attribute
selectors — already shipped and coherent. Tailwind's payoff (speed inside
agent loops, no naming) is real but front-loaded; retrofitting is churn.
Component libraries (shadcn-svelte, Skeleton) help most before the UI exists.
No change.

---

# Part 4 — Backend

## 13. FastAPI + SQLAlchemy + homegrown additive migrations — KEEP framework/ORM, FIX migrations

**FastAPI vs alternatives:** Django would have supplied auth, sessions, ORM,
migrations, and — the real loss — a free admin UI for back-office edits. But
Django's session/user machinery would fight the file-as-authority auth model
(§16), and its weight buys little for a 35-endpoint JSON API. Flask is FastAPI
minus types and OpenAPI. Litestar is a credible peer with a smaller community.
Node/Go would split the codebase across languages for zero gain. **FastAPI
stands** — but its auto-generated OpenAPI schema is currently unexploited
(§14).

**SQLAlchemy stands** — boring, typed, DB-agnostic (the SQLite→Postgres
escape hatch depends on it). SQLModel is a thinner wrapper with less maturity;
raw SQL would forfeit the model declarations the response models lean on.

**Migrations — FIX:** `init_db()` + `_migrate_added_columns()` handles
*additive* changes only. The first rename, drop, type change, or data backfill
has no path. **Adopt Alembic at that moment** (or proactively at the Postgres
switch): autogenerate diffs, versioned history, no more "did init_db run"
reasoning. Until then the homegrown approach is honestly fine — it's tested
(`test_migration.py`) and additive-only is a real discipline.

## 14. Hand-written TS API client with hand-duplicated types — FIX

`leads-api.ts` mirrors 35+ endpoints' shapes by hand. The codebase already
documents the failure mode this invites: an undeclared field on a backend
response model is *silently dropped*. FastAPI emits a complete OpenAPI schema
for free; running `openapi-typescript` in the build turns every drift into a
compile error. Keep the hand-written client *functions* (they're thin and
readable) — generate only the *types*. **Alternatives:** full client codegen
(orval, openapi-fetch — heavier, less readable output); tRPC-style end-to-end
types (doesn't exist across a Python/TS boundary); status quo (drift risk
compounds with every endpoint added).

## 15. SQLite + Litestream → R2 in production — KEEP\*

**Why picked:** zero-ops, single-file, free; Litestream gives continuous
off-site replication.

**Advantages:** for a write volume of "two humans clicking," SQLite is not a
compromise — it's the correct engine. No connection management, no managed-DB
bill, restore = `litestream restore`. The single-writer constraint is already
respected operationally (one machine, supervisord, `auto_stop` off).

**Disadvantages:** pins the app to one machine (no HA, restarts = downtime);
write concurrency limits if the product ever gets real multi-user write load;
some Postgres niceties (RLS §18, concurrent index builds) unavailable.

**Alternatives ranked:** managed Postgres now (Neon/Supabase/Fly PG — adds a
network hop, a bill, and an ops surface for zero current benefit); Turso/libSQL
(replicated SQLite at the edge — interesting, but single-region app +
vendor lock-in); keep. **Watch-trigger, explicitly:** the day a second machine,
a background-writer process, or >~10 concurrent writers appears, switch to
Postgres — the code is already DB-agnostic, `psycopg` is in requirements, and
testcontainers tests exist. Until then, keep.

## 16. Homegrown auth (users.txt + PBKDF2 + identity-only HS256 JWT, file re-read per request) — KEEP the model, FIX two implementation choices

**The model is better than it looks.** Identity-only JWT + per-request
re-authorization from the credentials file = instant revocation, no stale
claims, no session store. For 2–5 known users this beats managed auth
(Clerk/Auth0/Supabase Auth = an external dependency, a bill, and feature
surface — social login, MFA flows, orgs — nobody here needs). The
implementation is careful: constant-time compares, atomic file writes,
fail-closed boot, throttling, 33 test modules. Keep the model.

**FIX (a) — the backup hole:** `users.txt` lives on the Fly volume and is the
*only* irreplaceable state not replicated by Litestream. Lose the volume, lose
every credential. Two remedies, in order: (1) *now* — include `users.txt` in
an off-site copy (restic is already in the image; or a tiny rclone cron);
(2) *structural* — move credentials into the SQLite DB (a `credentials` table),
which Litestream then replicates for free. Per-request authority becomes a
trivial SELECT (cheaper than an mtime-cached file parse); `python -m app.users`
keeps working against the DB; the commit-guard problem disappears entirely.
The file loses one genuine virtue — editability when the DB is corrupt — which
the backup in (1) covers.

**FIX (b) — token transport:** the JWT sits in `localStorage`, readable by any
XSS. An **httpOnly, Secure, SameSite cookie** is strictly better for a
same-origin SPA — and it is also the natural vehicle for fixing §19, because
cookies ride along automatically on MapLibre tile fetches, PMTiles range
requests, and DuckDB-WASM parquet reads, where injecting an Authorization
header into three different libraries' fetch paths is genuinely fiddly. One
change solves two problems.

**Alternatives ranked (whole-system):** (1) creds-in-DB + httpOnly cookie
sessions — the target; (2) status quo + users.txt backup — acceptable
minimum; (3) managed auth — overkill until there are external users;
(4) passkeys — delightful, unnecessary at n=2.

## 17. PBKDF2-HMAC-SHA256 (stdlib) for password hashing — KEEP

argon2id is the stronger algorithm in a vacuum (memory-hardness defeats GPU
cracking), but it costs a native dependency, and the threat model here — a
mode-600 file (or DB row) holding 2–5 hashes, no SQLi surface into it, 240 K
iterations, constant-time verify — doesn't justify it. bcrypt's 72-byte limit
and another dependency likewise. Revisit only if credentials ever number in
the hundreds. No change.

## 18. Multi-tenancy: `tenant_id` column + per-store filtering (no RLS) — KEEP

App-level filtering is unverifiable-by-construction (one forgotten WHERE = a
leak), but the codebase mitigates the real risk: every query goes through a
tenant-scoped store class, and isolation has dedicated tests. With 1–2 tenants
who are the founders, the exposure is theoretical. **Alternatives:** Postgres
RLS (the principled answer — enforcement in the engine; adopt *if and when*
the Postgres trigger in §15 fires *and* tenants beyond the founding team
exist); separate DB per tenant (operational multiplication for n=2);
keep. No change now.

## 19. Static data tree served without authentication — FIX (the urgent one)

**Verified live during this review:** an unauthenticated request to
`https://morphyconsulting.com/data/processed/composite/owners_index.json`
returns `206` with content. The Caddyfile's `handle /data/processed/*` block is
a bare `file_server` — every parquet, PMTiles, GeoJSON, and the owners index
(names, mailing addresses, holdings) is downloadable by anyone with the URL.
The sign-in gate protects the UI shell and `/api/*` only. The `private,
no-store` headers show the *intent* was privacy; the enforcement is absent.

**How this happened (likely):** the static-data architecture (§10) predates
auth; when the front door was added, the API got a gate and the data tree was
overlooked because the *app* won't render without login.

**Options ranked:**

1. **Caddy `forward_auth` → tiny backend check endpoint, httpOnly session
   cookie (recommended).** Caddy asks the backend "is this request
   authenticated?" before serving any `/data/processed/*` byte; the cookie
   (from §16b) rides along automatically on *all* asset fetches — no header
   plumbing through MapLibre/PMTiles/DuckDB-WASM. Adds ~1 local round-trip per
   file request (cacheable in Caddy if needed). Smallest coherent fix.
2. **Signed URLs** (backend mints TTL'd tokens per session, appended as query
   params) — works, but threading the token through three JS libraries' fetch
   paths and handling expiry mid-session is the fiddly part forward_auth
   avoids.
3. **Cloudflare Access in front of `/data/*`** — fast to enable, but creates a
   *second* user store (Cloudflare accounts) divorced from `users.txt`, and
   couples auth to the CDN vendor.
4. **Move data behind the API** — destroys the range-request architecture
   (§10) that the whole read path is built on. No.

**Interim observation:** prod `index.json` is 20 bytes — worth a quick check
that the deployed composite is the intended current one.

---

# Part 5 — Deployment & operations

## 20. Fly.io, single VM, supervisord running uvicorn + Caddy + Litestream — KEEP

**Why picked:** cheapest coherent home for "one container, one volume, one
SQLite writer."

**Advantages:** one artifact, one machine, one mental model. supervisord-in-
container is unfashionable but *correct* here — the three processes share a
lifecycle and a volume by design (SQLite single-writer + its replicator + its
front door). Deploys, rollbacks, logs, and TLS handled by the platform.

**Disadvantages:** single point of failure (acceptable: restore =
re-deploy + `litestream restore`); Fly's reliability reputation is mixed —
mitigated by how little state is machine-local; 1 GB RAM bounds the owners
index (§31).

**Alternatives ranked:** Hetzner/DO VPS + compose (≈half the cost, but
patching/monitoring/TLS become your job — wrong trade for a 2-person team);
Render/Railway (same class as Fly, weaker volume + replica story, no
advantage); AWS (a complexity tax with no payoff at this scale);
Cloudflare-everything (Workers can't run this Python stack; would force a
rewrite). Keep.

## 21. Caddy as the edge — KEEP

Range/206 + gzip + history fallback + immutable-asset caching in 60 readable
lines; nginx offers the same at 3× the config friction; serving static from
FastAPI/uvicorn would put a Python event loop in front of multi-GB range
traffic. Caddy's `forward_auth` is also exactly the primitive §19 needs —
the choice pays for itself twice. No change.

## 22. deploy.sh (code via fly deploy, data via rclone → R2 → volume), no CD — KEEP, with one optional addition

The two-channel split (code vs. data) matches the two cadences; dry-run-by-
default on the data channel and a post-deploy smoke check are good engineering.
**Optional:** once frontend CI exists (§26), a deploy-on-main GitHub Action is
a small step — valuable mostly to remove "deploy from a dirty laptop" as a
failure mode. Not urgent.

## 23. PySide6 desktop puller — DECIDE (the most over-built corner of the repo)

**What it is:** 2,893 LOC of Qt across 11 files — source tree, progress bars,
walkthrough dialogs, diagnose button — wrapping the headless fetch/preprocess
libraries. Zero tests (the only untested subsystem). Pinned to
`PySide6==6.7.3` because 6.11 broke the macOS cocoa plugin — a ~700 MB
dependency with a known fragility, for an audience of one.

**What it actually earns its keep with:** the manual-walkthrough flow
(MANUAL_ONLY sources with click-through steps + file picker + manifest
stamping) and live preprocess progress. Real value, but nothing a terminal
can't render.

**Options ranked:**

1. **Freeze (recommended as immediate policy):** no new features into the Qt
   app; keep using it while it works. Costs nothing today.
2. **Replace with a Textual TUI when it next needs real work:** same
   walkthrough/progress affordances, ~⅓ the code, CI-testable, kills the
   PySide6 pin and 700 MB of dependency. The natural successor.
3. **Plain CLI + rich progress:** simplest possible; manual walkthroughs
   become printed steps — slightly worse UX for the click-through sources.
4. **Localhost web UI:** would reuse frontend skills but adds a server +
   browser dance to a local tool. Overkill.

The decision is the *policy*, not the rewrite: agree that the Qt app gets no
further investment, and pick its successor the day it breaks or needs a
feature.

---

# Part 6 — Engineering system

## 24. No Python packaging — `sys.path` hacks — FIX

`conftest.py`, `app_puller/__main__.py`, and the preprocess dialog all insert
`scripts/` into `sys.path` at runtime. It works until a file moves or a second
entry point appears. A minimal `[project]` table + `pip install -e .` (or uv
equivalent, §25) makes `fetch`/`preprocess` real packages, deletes every
sys.path line, and unlocks console-script entry points. An afternoon, mostly
deletion. **Alternatives:** keep (fragility compounds silently); full
workspace tooling (more than needed).

## 25. `requirements.txt` with `>=` pins, no lockfile — FIX

Today, CI, the Docker build, and a fresh laptop can all resolve *different*
transitive versions — and the geopandas/pyarrow/shapely stack is exactly where
transitive breaks happen. **Adopt `uv`:** `uv.lock` for reproducibility,
`uv sync` everywhere, 10–100× faster installs in CI/Docker as a side effect.
**Alternatives:** pip-tools (same idea, slower, older); Poetry (heavier
opinions than needed); status quo (a guaranteed eventually-lost morning).
Bundles naturally with §24.

## 26. CI gates: ruff + full pytest, frontend entirely ungated — FIX

The Python side is properly gated (lint + format + both test trees via
`testpaths`). The frontend has 34 unit tests, 13 e2e specs, and svelte-check —
*none of which run in CI*. A type error in `app/` lands green and explodes at
deploy-time `npm run build`. **Add a frontend job:** `npm ci && svelte-check
&& vitest run` — minutes of config. Playwright e2e needs real composite data;
run it locally / nightly rather than per-PR. **Alternatives:** status quo
(the gap is pure downside); gating e2e per-PR (data dependency makes it flaky
— don't).

## 27. No Python type checking — FIX (scoped)

ruff catches unused/undefined, not type errors. **Run pyright on `backend/`
only:** it's the smallest tree (≈10 K LOC), already type-annotated, and it
guards the only irreplaceable data (lead state). The pipeline can stay
unchecked indefinitely — pandas typing is miserable and the test suite carries
that weight. **Alternatives:** mypy (fine, slower, weaker inference); full-repo
checking (the pipeline would drown the signal in pandas noise); status quo.

## 28. Test posture — KEEP (genuinely good)

35 backend + 34 pipeline test modules, 34 unit + 13 e2e frontend specs,
golden-file fixtures, external-binary tests that skip cleanly, isolation tests
for tenancy, a commit-guard test for credentials. The only hole is the puller
(§23 — another argument for the TUI successor, which would be testable). The
e2e dependency on real AR+MT composites is a pragmatic trade — keep, just
don't gate PRs on it.

## 29. Domain logic duplicated across languages — FIX (cheap)

Two known sites: the lead-status ladder (`lead_status.py` ↔ `lead-status.ts`)
and filter semantics (DuckDB SQL ↔ JS owner predicates, §10). Inherent to the
Python/TS split; codegen from a single source is over-engineering at two
sites. **Do instead:** one shared JSON fixture per contract (status
transitions; filter cases with expected matches) consumed by *both* test
suites — divergence becomes a red test on whichever side moved. Revisit
codegen only if a third duplication site appears.

## 30. Monorepo without workspace tooling — KEEP

One repo, four roots (app, backend, scripts, app_puller), no
workspace manager. At this scale workspace tooling (nx, turbo, uv workspaces)
manages a problem that doesn't exist. The actual pain points are §24/§25, not
the repo shape. No change.

---

# Part 7 — Forward-looking

## 31. Owners index as in-memory JSON in the backend — KEEP\*

Loaded whole at import, served from RAM, overrides applied at read time with a
single-owner fast path. Correct at 4 states. **The cliff:** Python's JSON
object overhead is 3–5× file size, on a 1 GB VM that also runs Caddy and
Litestream. **Watch-trigger:** when `owners_index.json` approaches ~100 MB
(or states ×3), move the read path to SQLite or server-side DuckDB over the
parquet — the `OwnersIndexService` interface already isolates the swap.

## 32. Claude API for the planned lease-document extraction (D+E) — KEEP, with one design rule

The provider choice is sound (document extraction is a core strength; the SDK
is already a dependency; the team has deep familiarity). The one architectural
request: put extraction behind a thin internal interface (input: doc bytes;
output: typed lease fields + confidence + provenance) so the provider/model is
swappable and the extraction layer is testable with fixtures, not API calls.
Evaluate models/pricing at build time against current docs rather than baking
assumptions in now.

---

# What this review deliberately did *not* find

No finding of: wrong language anywhere, wrong framework anywhere, wrong
database, wrong map stack, wrong deployment model, or any subsystem needing a
rewrite. The foundation is sound. The urgent item (§19) is a gap between two
individually-correct decisions (static data architecture + frontend auth
gate), not a flawed decision. The remaining fixes are engineering-system
hygiene (lockfile, packaging, CI gating, type generation) — cheap, and they
compound.
