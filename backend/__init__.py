"""Lead-triage write-layer backend (ADR-055 / ADR-061).

Slice 1 (tracer): the first backend code in the repo. A tenant-shaped
FastAPI + Postgres service that holds the *write* layer (Lead status +
notes + contact attempts) on top of the static, read-only owners index
the preprocess pipeline precomputes. The analytical read-layer (PMTiles,
DuckDB-WASM, catalog GeoJSON) is unchanged and lives outside this package.

This package never imports the preprocess framework; it only *reads* the
static ``owners_index.json`` it produces (ARCHITECTURE.md §5.3).
"""
