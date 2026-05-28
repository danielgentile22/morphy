# pilot

**Cell-tower ground-lease renegotiation analytics.** Joins tower locations to parcel records to economic-distress overlays, then layers carrier identification + lease document storage + LLM-based extraction + triage workflow into a co-founder-facing product. **Phase 1** covers four anchor states (AR + MT + FL + NC) with freestanding towers; **Phase 2** adds rooftop installations + operational scale.

> 🔀 **2026-05-25 phase shift:** previously a "v1 pitch-quality demo," this is now Phase 1 of a fleshed-out internal product the business co-founder uses daily for triage — see [docs/adr/0053-product-phase-shift.md](docs/adr/0053-product-phase-shift.md) for the reframe and ADRs 053–059 in [docs/adr/](docs/adr/) for the locked decisions.

> Read [docs/SCOPE.md](docs/SCOPE.md) first for what's being built right now. Read [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for the business case.

---

## Four subsystems

| Subsystem | Path | Purpose |
|---|---|---|
| **Data Puller** | `app_puller/` | PySide6 desktop UI; fetches raw data into `data/raw/<source_id>/current/`. |
| **Preprocess pipeline** | `scripts/preprocess/` | Registry-driven Normalizer + Join + View framework; per-state Composer. |
| **Map app** | `app/` | Svelte 5 + MapLibre analytical SPA — PMTiles parcels + DuckDB-WASM filtering + tunable scoring (Slice 3). See [app/ARCHITECTURE.md](app/ARCHITECTURE.md). |
| **Backend** *(Slice 4 — in design)* | `backend/` | FastAPI + Postgres + S3-compatible + magic-link auth + Claude API. Holds lead state, lease document PDFs, LLM-extracted lease fields, activity log, scoring profiles, owner-cluster overrides. Per [ADR-055](docs/adr/0055-hosted-private-backend.md). |

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) has the full system diagram + data flow.

---

## Quick start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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
| Florida | 12 | 🔴 Raw intact (all 67 counties); normalized + composite deleted 2026-05-20 — needs re-normalize + compose (Slice F) |
| North Carolina | 37 | 🔴 All raw data deleted 2026-05-20 — needs full re-fetch, normalize, and compose (Slice F) |

See [docs/SCOPE.md §2](docs/SCOPE.md) for why these, and [docs/STATUS.md](docs/STATUS.md) for the live state.

---

## Repository layout

```
pilot/
├── README.md                 (you are here)
├── CONTEXT.md                Canonical product language (glossary)
├── CLAUDE.md                 AI-agent orientation
├── PROJECT_BRIEF.md          Business case
├── requirements.txt
├── app/                      Svelte 5 + MapLibre map app
├── app_puller/               PySide6 desktop puller
├── backend/                  FastAPI + Postgres + S3 + Claude API  (Slice 4 — in design)
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
│   ├── adr/                  Architecture Decision Records (ADR-053+; legacy in docs/DECISIONS.md)
│   ├── archive/              Historical docs (preprocess v1, etc.)
│   ├── pitch-assets/         Screenshots / GIFs
│   └── research/             Data-source legal/license research
└── tests/                    (preprocess tests; backend tests live under backend/tests/)
```

---

## License + status

This is a **Phase 1 internal product** for a 2-person team (dev + business co-founder); the co-founder is the daily user. Outputs contain parcel-owner names + mailing addresses (PII when combined) — treat per [docs/SECURITY.md](docs/SECURITY.md). The repo itself is private; backend (Slice 4) deploys hosted-private with magic-link auth per [ADR-055](docs/adr/0055-hosted-private-backend.md).

**Phase 1 slice plan** (untimed, goal-driven):

1. **F** — Finish FL + NC composes (chunked compose ADR-051 + NC re-fetch) — **next up**
2. **A** — FCC ULS carrier identification (Cellular + PCS + AWS / 700 MHz)
3. **C** — Asset enrichment (billboards + solar on parcel) + tunable scoring UI
4. **D + E** — Lease doc upload + LLM extraction + triage state / write layer / CSV exports (**backend stands up here**)
5. **B** — Vendor (tower-co) inference

Per-slice "shipped" gates in [docs/GOALS.md §3](docs/GOALS.md). Overall outcome bar: co-founder uses the product as his primary daily triage tool for 4 consecutive weeks.

See [docs/STATUS.md](docs/STATUS.md) for the live snapshot.
