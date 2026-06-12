"""Alembic migration environment (PRD #134).

The app's metadata imports under either of its two runtime names: ``app.*``
inside the deployed container (uvicorn runs ``app.main:app`` from
/srv/backend) or ``backend.app.*`` on a dev checkout / under pytest. The
container name is tried first so a boot-time upgrade reuses the already-
imported modules instead of re-importing the package under a second name.

The boot path (``db.init_db``) hands its live Engine over via
``config.attributes["connection"]``; the CLI builds one from the app's
``DATABASE_URL`` instead — there is no URL in alembic.ini.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

try:  # container import name first — see module docstring
    from app.config import settings
    from app.db import Base

    from app import models  # noqa: F401 — registers every table on Base.metadata
except ImportError:
    from backend.app import models  # noqa: F401
    from backend.app.config import settings
    from backend.app.db import Base

config = context.config
# CLI logging; keep existing loggers so a boot-time run never silences the app's.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _configure_and_run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite barely ALTERs in place; batch mode rebuilds the table so one
        # revision file runs on both engines (Postgres ignores it).
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` — preview the DDL without a database."""
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=url.startswith("sqlite"),
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection", None)
    if connectable is None:
        connectable = create_engine(settings.database_url)
    if isinstance(connectable, Connection):
        _configure_and_run(connectable)
    else:
        with connectable.connect() as connection:
            _configure_and_run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
