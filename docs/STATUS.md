# Status: what shipped and where it stopped

morphy is archived. This doc records what Phase 1 set out to build, what shipped, and what
was still unbuilt when work stopped in mid-2026. The dated trail is in
[CHANGELOG.md](./CHANGELOG.md), and the reasoning behind each choice is in the ADRs
([DECISIONS.md](./DECISIONS.md)).

## 1. What Phase 1 was

Phase 1 was a working triage tool for one analyst. The analyst opened the app, filtered and
ranked cell-tower landowners across four states, marked lead status, and logged contact
attempts. The tool had to answer a question no public dataset answers directly:
who owns the land under this tower?

Phase 1 covered freestanding towers only. Rooftop and in-building sites need a different
(mostly paid) data foundation, so they were left for a later phase that never happened
([ADR-054](./adr/0054-asset-universe-phase-1-2.md)). The shift from an earlier pitch demo to
this product cut is recorded in [ADR-053](./adr/0053-product-phase-shift.md).

## 2. States

Geographic scope was set per state ([ADR-001](./adr/0001-state-level-geographic-scope.md)),
because parcel data is published per state or per county with no free national source.

| State | FIPS | Outcome | Detail |
|---|---|---|---|
| Arkansas | 05 | Composed | 2,116,976 parcels, 11 joins, 8 views, 0 warnings. |
| Montana | 30 | Composed | 920,111 parcels across all 56 counties. |
| Florida | 12 | Composed | 11,425,608 parcels (Florida Department of Revenue tax roll for all 67 counties, plus state-owned land), built with chunked compose ([ADR-051](./adr/0051-chunked-compose.md)). |
| West Virginia | 54 | Composed | 1,389,855 parcels across all 55 counties from the statewide geodatabase ([ADR-060](./adr/0060-wv-committed-anchor.md)). |
| North Carolina | 37 | Deferred | The original test state. Raw data was deleted, and the one re-fetch attempt stopped partway, because the NC OneMap service returned intermittent HTTP 504s at deep pagination offsets ([ADR-048](./adr/0048-nc-onemap-mapserver-pagination.md)). |
| Indiana, Utah | 18, 49 | Dropped | Their free parcel layers carry no owner names ([ADR-017](./adr/0017-indiana-dropped.md), [ADR-049](./adr/0049-utah-dropped.md)). |
| Minnesota | 27 | Dropped | License terms were ambiguous ([ADR-018](./adr/0018-minnesota-deferred.md)). |

Two West Virginia details needed code of their own. Owner, value and land-use fields live in a
separate `ParcelSummary` table joined on `CleanParcelID`. And the state's internal `CountyID`
(01-55) is not a Census FIPS code, so county resolution uses an explicit verified lookup table
(`scripts/preprocess/normalizers/state_parcel_adapters/wv.py`). West Virginia parcels record the
surface owner. Split estates are common there, so surface ownership must not be read as
mineral ownership.

## 3. The slice plan

Phase 1 was planned as five slices, ordered F, A, C, D+E, B. The triage write layer and the
lead-centric UI were later pulled forward ahead of A and C
([ADR-061](./adr/0061-lead-centric-triage-redesign.md)).

| Slice | Goal | Outcome |
|---|---|---|
| F | Compose the four anchor states | Shipped. |
| A | Identify wireless carriers per tower from FCC Universal Licensing System (ULS) licenses | Shipped, with lower coverage than planned (see below). |
| C | Enrich parcels with solar and billboards, and ship tunable scoring | Scoring and solar shipped. Billboards stayed a no-op. |
| D+E | Lease upload, LLM extraction, triage state, backend, CSV export | Backend and triage shipped. Lease upload, extraction and CSV export were never built. |
| B | Infer the tower company (vendor) that owns each structure | Never started. |

## 4. What shipped

- **The data pipeline.** A registry of 17 active sources (12 more registered but deferred)
  feeds a Normalizer → Join → View → Compose framework
  ([ADR-002](./adr/0002-registry-driven-architecture.md)). DuckDB does the heavy lifting, and
  chunked compose keeps Florida's 11 million parcels under the memory ceiling. Each state
  composes 11 joins and 8 views, linking FCC Antenna Structure Registration (ASR) towers to
  parcels and to distress overlays from HUD (Opportunity Zones and Qualified Census Tracts),
  the Appalachian Regional Commission, and USDA persistent-poverty counties.
- **The data TUI.** `python -m data_tui` runs the full lifecycle from one terminal app: pull,
  preprocess, verify, and a confirm-gated data deploy. 16 of the 17 active sources fetch
  automatically. Arkansas parcels stay manual because the publisher's terms require it. The TUI
  replaced an earlier Qt desktop puller, which was deleted.
- **The map app.** Svelte 5 and MapLibre, with parcels served as PMTiles and filtered in the
  browser by DuckDB-WASM. Three sections: Dashboard, Explore, Leads
  ([ADR-065](./adr/0065-redesign-three-section-ia.md)).
- **The backend.** FastAPI and SQLAlchemy, with `tenant_id` on every table and every route
  ([ADR-055](./adr/0055-hosted-private-backend.md)). It stores leads, tasks, contact attempts,
  the activity log, scoring presets and owner merge/split overrides. Auth is username and
  password with credentials in the database and an identity-only JWT in an httpOnly cookie
  ([ADR-062](./adr/0062-username-password-replaces-magic-link.md),
  [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md),
  [ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)). Schema changes
  ship as Alembic revisions; the head is `0003`.
- **The public read-only demo.** [morphy-demo.fly.dev](https://morphy-demo.fly.dev) runs with
  `DEMO_MODE` on. "Explore the demo" signs a visitor in, with no password, as a read-only
  credential whose writes the backend refuses with 403. Its board holds six fictional leads
  seeded over government owners
  ([ADR-077](./adr/0077-read-only-demo-credential.md), [ADR-078](./adr/0078-demo-leads-over-government-owners.md)). The same change removed the unused
  in-catalog LLM helper and its log table.
- **Hosting.** One always-on Fly machine running Caddy, the API and Litestream, with SQLite on
  a volume replicated to Cloudflare R2 ([ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md)).
  Caddy gates the static data files with the same session check as the API.
- **Carrier identification (Slice A).** ULS licenses are matched to ASR structures and shown as
  "licensed in this area, not a confirmed tenant"
  ([ADR-074](./adr/0074-uls-carrier-rearchitecture.md)). The plan called for at least 70% of
  towers to carry a carrier. Measured coverage was 6-17% per state. Most ASR structures have no
  per-site ULS license, so coverage is bounded by the source rather than the join, and an empty
  carrier list is the normal case.
- **Tunable scoring (Slice C).** Each tower gets a transparent score whose weights the analyst
  can change live, with named presets
  ([ADR-058](./adr/0058-tunable-transparent-scoring.md),
  [ADR-073](./adr/0073-interestingness-reweight.md)). Solar facilities join to parcels.
- **Owner resolution.** Leads are owner clusters
  ([ADR-056](./adr/0056-lead-equals-owner-cluster.md)). A cross-state owners index keys owners
  by name plus state, with a curated alias table that re-merges the four national tower
  companies ([ADR-075](./adr/0075-cross-state-owner-identity.md)). The analyst can merge and
  split clusters by hand. The override resolves in one place
  (`display_cluster_id = coalesce(override_target, raw_cluster_id)`).
- **Data-quality fixes.** A data audit in June 2026 produced ADR-070 through ADR-076:
  statutory assessed value, solar feed dedup, FAA and ASR tower dedup, a reweighted default
  score, the carrier rework, cross-state owner identity, and an expanded owner-type classifier.

## 5. What was never built

- **Lease upload and LLM extraction.** The design is in
  [ADR-059](./adr/0059-llm-lease-extraction.md): extraction with per-field citations and
  self-rated confidence, gated on a hand-labelled 20-lease gold set at 85% field accuracy. No
  lease or extraction code exists.
- **Vendor inference (Slice B).** The plan was to infer the current tower company from the ASR
  registrant plus a portfolio roll-up heuristic.
- **Billboards.** Normalizers for state DOT billboard permits and a `BillboardToParcelJoin` are
  registered, but no anchor state has billboard data on disk, so the join runs as a no-op.
- **Lease-rate comparables.** A free county-level lease-rate dataset was assumed to exist. It
  does not, and no replacement source was wired in.
- **An LLM eval suite.** The ADR-059 accuracy harness was the one unbuilt test layer
  ([TESTING.md](./TESTING.md)).

## 6. Lessons worth keeping

- **One recipe, two producers.** The cross-state owner key changed from name-only to name plus
  state in `owners_index.py`, but `national_towers.py` still baked tower cluster ids with the
  old key. The map narrows its tower layer by the owners-index id set, so the two diverged and
  the layer collapsed to the four curated tower companies. The fix baked
  `cross_state_owner_key(name, state_fips)` into both producers. The parity test had pinned
  `national_towers` to the client rather than to the owners index, which is why the drift got
  through.
- **Coverage gates should follow measurement.** The 70% carrier-coverage target was set before
  anyone measured how many ASR structures have per-site licenses.

## 7. Deliberate non-goals

| Item | Why |
|---|---|
| Rooftop installations | Different asset universe with mostly paid data ([ADR-054](./adr/0054-asset-universe-phase-1-2.md)). |
| Nationwide coverage | Needs a paid national parcel source such as Regrid ([ADR-012](./adr/0012-regrid-deferred.md), [ADR-057](./adr/0057-budget-posture-reframed.md)). |
| LLC unmasking beyond public Secretary of State officer disclosures | Permanent non-goal on privacy grounds ([ADR-041](./adr/0041-no-llc-unmasking.md), narrowed by ADR-057). |
| Mass email and CRM automation | The tool surfaced leads and logged activity. Contact happened outside it. |
| Real-time data | Pulls were manual-trigger, with freshness shown in the UI ([DATA_FRESHNESS.md](./DATA_FRESHNESS.md)). |

## 8. Scaling limits of the single-machine design

Neither limit was reached at Phase 1 scale.

- **The owners index is served as in-memory JSON.** Python's JSON overhead is roughly 3-5x the
  file size, on a 1 GB VM that also runs Caddy and Litestream. Near 100 MB of
  `owners_index.json` the read path should move to SQLite or server-side DuckDB over the
  parquet. `OwnersIndexService` already isolates that swap.
- **SQLite allows one writer.** A second machine, a background writer, or more than about ten
  concurrent writers would call for Postgres. The code is database-agnostic, `psycopg` ships,
  and testcontainers tests exist. Postgres row-level security would be the follow-on for
  engine-enforced tenant isolation.
