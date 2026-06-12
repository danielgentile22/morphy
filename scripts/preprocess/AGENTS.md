# Preprocess pipeline (ETL framework)

The Normalizer → Join → View → Compose framework that turns raw source data into
the composite map/owner artifacts the app and backend read. Owns canonical schemas,
clustering, the owners index, scoring, tiles, and app-asset generation. Does NOT
fetch data (that's `../fetch/`) or hold any write state (that's `../../backend/`).

**Deep dives:** [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) §3 (the framework),
CLAUDE.md §5.7 (adding a normalizer), §8 (code conventions).

## Entry points
- `pipeline.py`, `runner.py`, `compose.py` — orchestration (driven by `scripts/preprocess.py`).
- `registry.py` — normalizers register here.
- `normalizers/<source>.py` — `@register_normalizer`, declares `canonical_types`.
- `normalizers/state_parcels.py` (+ `state_parcel_adapters/`) — per-state field maps.
- `joins/`, `views/` — spatial joins + filtering views.
- `duck.py` — DuckDB session helper (PRD #135): connection + spatial extension +
  sharded-parquet registration. **The only module that manages DuckDB connections.**
- `owners_index.py` — the cross-state owners index (schema-versioned; backend reads it).
- `cluster.py` — conservative owner clustering (errs toward *not* merging).
- `app_assets.py`, `tiles.py` — index.json / facets / parquet / PMTiles writers.

## Contracts & invariants
- **All spatial output is EPSG:4326 (WGS84 lat/lon).** Reproject every spatial output.
- **No new normalize-time filtering** — full-fidelity raw preservation. Keep all rows;
  add status/validity columns; let Joins and Views filter.
- **Use `safe_merge`** (ADR-020) when a Join adds columns a Normalizer placeholdered.
- **Owners index is schema v4**: bump `OWNERS_INDEX_SCHEMA_VERSION` on change, give new
  fields safe defaults (a stale index must still serve downstream). Mirror any field the
  backend serves onto its `Structure`/`OwnerSummary` model — see [`../../backend/AGENTS.md`](../../backend/AGENTS.md).
- **Never bake owner merge/split overrides into the parquet.** Raw cluster ids stay
  untouched; overrides are a backend read-time concern.
- Clustering stays conservative: a false merge is a wrong-person call.
- **DuckDB stages must be output-equivalent to what they replaced** (PRD #135):
  define the per-stage equivalence (rows, key columns, aggregates) before
  migrating, pin it with a legacy-vs-DuckDB harness test
  (`tests/test_duckdb_equivalence.py`), and delete the streaming code the stage
  made dead. Geometry repair/reprojection stays in geopandas at normalize time.

## Patterns
New normalizer: create `normalizers/<source>.py`, `@register_normalizer`, declare
`canonical_types`, add to `registry.py`, add a fixture + test. Full checklist: CLAUDE.md §5.

## Run
`python scripts/preprocess.py [--state NN | --app-assets | --tiles | --rebuild-manifest]`

## Related context
- Where raw data comes from: [`../fetch/AGENTS.md`](../fetch/AGENTS.md)
- Who reads the output: [`../../backend/AGENTS.md`](../../backend/AGENTS.md), [`../../app/AGENTS.md`](../../app/AGENTS.md)
