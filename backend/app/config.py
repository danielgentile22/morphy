"""Backend settings — environment-driven, with dev-friendly defaults.

Slice 1 keeps this minimal: a database URL, the path to the static
owners index, and the stubbed tenant id (real magic-link auth that
resolves a tenant is Slice 2 / #48). The default database is a local
SQLite file so the backend runs with zero external services; point
``DATABASE_URL`` at Postgres (``postgresql+psycopg://…``) in deploy/CI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# repo root = backend/app/config.py → parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSITE_ROOT = PROJECT_ROOT / "data" / "processed" / "composite"


@dataclass(frozen=True)
class Settings:
    database_url: str
    owners_index_path: Path
    # Stubbed until magic-link auth lands (ADR-055: "always reads 1 for now").
    stub_tenant_id: int
    cors_origins: tuple[str, ...]

    @staticmethod
    def from_env() -> Settings:
        default_db = (
            f"sqlite+pysqlite:///{PROJECT_ROOT / 'data' / 'processed' / 'lead_state.sqlite3'}"
        )
        return Settings(
            database_url=os.environ.get("DATABASE_URL", default_db),
            owners_index_path=Path(
                os.environ.get("OWNERS_INDEX_PATH", str(COMPOSITE_ROOT / "owners_index.json"))
            ),
            stub_tenant_id=int(os.environ.get("STUB_TENANT_ID", "1")),
            cors_origins=tuple(
                o.strip()
                for o in os.environ.get(
                    "CORS_ORIGINS",
                    "http://localhost:5173,http://localhost:4173",
                ).split(",")
                if o.strip()
            ),
        )


settings = Settings.from_env()
