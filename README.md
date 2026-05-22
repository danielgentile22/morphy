# pilot

Feasibility prototype for **cell-tower ground-lease renegotiation
analytics**. Joins tower locations to parcel records to economic-distress
overlays, using only free public data. Currently focused on a 3–5 state
pitch-quality cut.

> Read [docs/SCOPE.md](docs/SCOPE.md) first if you want to know what we're
> building right now. Read [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for the
> business case.

---

## Three subsystems

| Subsystem | Path | Purpose |
|---|---|---|
| **Data Puller** | `app_puller/` | PySide6 desktop UI; fetches raw data into `data/raw/<source_id>/current/`. |
| **Preprocess pipeline** | `scripts/preprocess/` | Registry-driven Normalizer + Join + View framework; per-state Composer. |
| **Map app** | `app/` | Svelte 5 + MapLibre analytical SPA — PMTiles parcels + DuckDB-WASM filtering. See [app/ARCHITECTURE.md](app/ARCHITECTURE.md). |

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) has the full system diagram
+ data flow.

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
- [docs/MAP_APP_REHAUL.md](docs/MAP_APP_REHAUL.md) — map app v2 plan (realized — now live at `app/`)
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — version history

**Working with AI coding agents:**

- [CLAUDE.md](CLAUDE.md) — orientation for Claude Code sessions

---

## Anchor states for v1

| State | FIPS | Status |
|---|---|---|
| Arkansas | 05 | ✅ Working end-to-end |
| Montana | 30 | ✅ Working end-to-end |
| Florida | 12 | 🔴 Raw intact (all 67 counties); normalized + composite deleted 2026-05-20 — needs re-normalize + compose |
| North Carolina | 37 | 🔴 All raw data deleted 2026-05-20 — needs full re-fetch, normalize, and compose |

See [docs/SCOPE.md §2](docs/SCOPE.md) for why these, and
[docs/STATUS.md](docs/STATUS.md) for the live state.

---

## Repository layout

```
pilot/
├── README.md                 (you are here)
├── CLAUDE.md                 AI-agent orientation
├── PROJECT_BRIEF.md          Business case
├── requirements.txt
├── app/                      Svelte 5 + MapLibre map app
├── app_legacy_v1/            Leaflet map (v1, retired)
├── app_puller/               PySide6 desktop puller
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
│   ├── archive/              Historical docs (preprocess v1, etc.)
│   └── pitch-assets/         Screenshots / GIFs for pitch deck
└── tests/                    (added in Section 6 of work plan)
```

---

## License + status

This is a **feasibility prototype**, not a released product. Outputs
contain parcel-owner names + mailing addresses (PII when combined) —
treat per [docs/SECURITY.md](docs/SECURITY.md). The repo itself is
private until access controls land.

In-flight production-readiness push: Sections 1–3 are done, Section 4
complete for AR/MT (FL raw intact; NC raw deleted and needs re-fetch),
Section 5 (preprocess code hygiene) in progress — see
[docs/STATUS.md](docs/STATUS.md).
