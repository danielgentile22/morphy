# pilot

**Cell-tower ground-lease renegotiation analytics.** Joins tower locations to parcel records to economic-distress overlays, then layers carrier identification + lease document storage + LLM-based extraction + triage workflow into a co-founder-facing product. **Phase 1** covers four committed anchor states (AR + MT + FL + WV) with freestanding towers (NC deferred to a Phase-1 stretch candidate); **Phase 2** adds rooftop installations + operational scale.

> 🔀 **2026-05-25 phase shift:** previously a "v1 pitch-quality demo," this is now Phase 1 of a fleshed-out internal product the business co-founder uses daily for triage — see [docs/adr/0053-product-phase-shift.md](docs/adr/0053-product-phase-shift.md) for the reframe and ADRs 053+ in [docs/adr/](docs/adr/) (indexed by [docs/DECISIONS.md](docs/DECISIONS.md)) for the locked decisions.

> Read [docs/SCOPE.md](docs/SCOPE.md) first for what's being built right now. Read [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for the business case.

---

## Four subsystems

| Subsystem | Path | Purpose |
|---|---|---|
| **Data Puller** | `app_puller/` | PySide6 desktop UI; fetches raw data into `data/raw/<source_id>/current/`. |
| **Preprocess pipeline** | `scripts/preprocess/` | Registry-driven Normalizer + Join + View framework; per-state Composer. |
| **Map app** | `app/` | Svelte 5 + MapLibre analytical SPA — three-section IA (Dashboard · Explore · Leads), PMTiles parcels + DuckDB-WASM filtering + tunable scoring. See [app/ARCHITECTURE.md](app/ARCHITECTURE.md). |
| **Backend** | `backend/` | FastAPI + SQLAlchemy lead-triage write-layer — tenant-scoped lead + task state, contact attempts, owner merge/split overrides; username/password auth ([ADR-062](docs/adr/0062-username-password-replaces-magic-link.md)/[063](docs/adr/0063-file-credentials-teams-per-request-authority.md)/[069](docs/adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)). Deployed in production. S3 lease-doc storage + Claude API extraction still planned. Per [ADR-055](docs/adr/0055-hosted-private-backend.md). See [backend/README.md](backend/README.md). |

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) has the full system diagram + data flow.

---

## Quick start

```bash
# One-time: install uv (https://docs.astral.sh/uv/getting-started/installation/)
brew install uv

# One command = the whole working environment: creates .venv on Python 3.11
# from uv.lock (exact pinned versions, all dependency groups) and installs
# fetch/preprocess editable so imports work with no path hacks (PRD #132).
uv sync
source .venv/bin/activate
```

### 1. Pull raw data

```bash
python -m app_puller
```

In the puller: **Check for updates** → **Pull all missing**. For
MANUAL_ONLY sources, click **Walk me through** on each row.
[docs/PULLER_UX.md](docs/PULLER_UX.md) is the design spec.

### 2. Preprocess

```bash
python scripts/preprocess.py                    # all sources + all states
python scripts/preprocess.py --state 05         # just Arkansas
python scripts/preprocess.py --source ar_parcels --force-rebuild
python scripts/preprocess.py --rebuild-manifest # resync manifest with disk
python scripts/preprocess.py --list-views       # discoverability
```

Outputs:

- `data/processed/normalized/<source>/` — canonical-schema Parquet +
  GeoJSON + `raw.parquet` + `quality_report.json`.
- `data/processed/composite/<state_fips>/` — joined per-state outputs +
  views + `catalog.json` + `summary.json`.

### 3. Generate the app's data assets

```bash
python scripts/preprocess.py --app-assets   # index.json + per-state facets / slim parquet / county boundaries
python scripts/preprocess.py --tiles        # per-state parcels.pmtiles (needs tippecanoe)
```

### 4. Run the map app

```bash
python scripts/serve.py 8765                # range-capable data server, from the repo root
cd app && npm install && npm run dev        # http://localhost:5173  (?state=05 to deep-link)
```

`npm run build` produces `app/dist/`. The state selector auto-populates
from `data/processed/composite/`. See [app/ARCHITECTURE.md](app/ARCHITECTURE.md).

### 5. Tests

```bash
pytest                                      # preprocess pipeline (incl. the app-asset scripts)
ruff check . && ruff format --check .
uv run pyright                              # type-check the backend (basic mode, backend/ only — PRD #136)
cd app && npm run check && npm run test:unit && npm run test:e2e
```

---

## Where to look

**Front door** (start here):

- [docs/SCOPE.md](docs/SCOPE.md) — what's in / out of the current cut
- [docs/STATUS.md](docs/STATUS.md) — what works today
- [docs/GOALS.md](docs/GOALS.md) — success criteria

**Deep dives:**

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the system fits together
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) — per-source schema + license + automation policy
- [docs/DATA_FRESHNESS.md](docs/DATA_FRESHNESS.md) — when each source needs a refresh
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md) — caveats and pre-commercial blockers
- [docs/SECURITY.md](docs/SECURITY.md) — PII / data-handling posture
- [docs/GLOSSARY.md](docs/GLOSSARY.md) — domain-term reference

**Where we're going:**

- [docs/ROADMAP.md](docs/ROADMAP.md) — past / present / future
- [docs/DECISIONS.md](docs/DECISIONS.md) — locked-in design choices
- [docs/adr/](docs/adr/) — per-ADR architecture decision records

**Working with AI coding agents:**

- [CLAUDE.md](CLAUDE.md) — orientation for Claude Code sessions

---

## Anchor states for Phase 1

| State | FIPS | Status |
|---|---|---|
| Arkansas | 05 | ✅ Working end-to-end |
| Montana | 30 | ✅ Working end-to-end |
| Florida | 12 | ✅ Recomposed 2026-05-29 (all 67 counties) — live in the app; county-score gap closed (`county_scores` layer + tower/solar distress joins now present), consistent with AR/MT. See [STATUS §4.1](docs/STATUS.md) |
| West Virginia | 54 | ✅ Added 2026-05-29 (PR #44) — `wv_parcels` statewide layer (WVGISTC, SB 588); composed (1,389,855 parcels, all 55 counties) + live in the app. **Committed anchor** (ADR-060, 2026-05-29). See [STATUS §4.4](docs/STATUS.md) |
| North Carolina | 37 | ⏸️ Deferred / Phase-1 stretch — raw data deleted 2026-05-20; re-fetch + normalize + compose deferred (NC OneMap re-fetch intermittently 504s). Not a committed anchor. |

The four committed anchors are AR + MT + FL + WV (WV elevated 2026-05-29, ADR-060). See [docs/SCOPE.md §2](docs/SCOPE.md) for why these, and [docs/STATUS.md](docs/STATUS.md) for the live state.

---

## Repository layout

```
pilot/
├── README.md                 (you are here)
├── CONTEXT.md                Canonical product language (glossary)
├── CLAUDE.md                 AI-agent orientation
├── PROJECT_BRIEF.md          Business case
├── pyproject.toml            Project + dependency groups (uv; uv.lock pins exact versions)
├── app/                      Svelte 5 + MapLibre map app
├── app_puller/               PySide6 desktop puller
├── backend/                  FastAPI + SQLAlchemy lead-triage write-layer (auth, teams-as-tenants; SQLite dev / Postgres) — see backend/README.md
├── scripts/
│   ├── preprocess.py         CLI wrapper
│   ├── preprocess/           Normalizer/Join/View framework
│   ├── fetch/                Headless puller library
│   ├── verify_raw.py         File-signature contents check
│   └── diagnose.py           LLM-powered verify diagnosis
├── data/                     (git-ignored; ~15 GB raw)
│   ├── raw/<source>/current/
│   └── processed/{normalized,composite}/
├── docs/                     All deep-dive documentation
│   ├── adr/                  Architecture Decision Records (all ADRs; indexed by docs/DECISIONS.md)
│   ├── agents/               Skill-system configuration
│   └── research/             Data-source legal/license research
└── tests/                    Preprocess + app-asset tests (backend tests live under backend/tests/)
```

---

## License + status

This is a **Phase 1 internal product** for a 2-person team (dev + business co-founder); the co-founder is the daily user. Outputs contain parcel-owner names + mailing addresses (PII when combined) — treat per [docs/SECURITY.md](docs/SECURITY.md). The repo itself is private; the backend deploys hosted-private with username/password auth per [ADR-055](docs/adr/0055-hosted-private-backend.md) / [ADR-062](docs/adr/0062-username-password-replaces-magic-link.md).

**Phase 1 slice plan** (untimed, goal-driven):

1. **F** — Committed anchors (AR + MT + FL + WV) composed — **✅ shipped**
2. **A** — FCC ULS carrier identification (Cellular + PCS + AWS / 700 MHz) — **✅ shipped** (~6–17% coverage)
3. **C** — Asset enrichment (billboards + solar on parcel) + tunable scoring UI — **✅ scoring UI shipped** (billboards await anchor raw data)
4. **D + E** — Lease doc upload + LLM extraction + triage state / write layer / CSV exports — backend + triage **shipped**; **lease upload + LLM extraction is the next unbuilt work**
5. **B** — Vendor (tower-co) inference — not started

Per-slice "shipped" gates in [docs/GOALS.md §3](docs/GOALS.md). Overall outcome bar: co-founder uses the product as his primary daily triage tool for 4 consecutive weeks.

See [docs/STATUS.md](docs/STATUS.md) for the live snapshot.
