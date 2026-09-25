"""Alembic migration environment.

DATABASE_URL must be set in the environment before running Alembic.
Accepts plain postgresql:// or postgres:// URLs — the driver prefix is
normalised to postgresql+psycopg2:// for the sync migrations connection.
"""
import os
import re
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# ---------------------------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Resolve DATABASE_URL from environment
# ---------------------------------------------------------------------------
_raw_url = os.environ.get("DATABASE_URL", "")
if not _raw_url:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Export it before running Alembic:\n"
        "  export DATABASE_URL=postgresql://user:pass@host:5432/viveka"
    )

# Normalise scheme: strip any existing driver suffix, then force psycopg2
_url = re.sub(r"^postgres(?:ql)?(?:\+\w+)?://", "postgresql+psycopg2://", _raw_url)
config.set_main_option("sqlalchemy.url", _url)

# ---------------------------------------------------------------------------
# Import all ORM models so Alembic can detect schema drift via autogenerate
# ---------------------------------------------------------------------------
# Importing base registers all models in Base.metadata
from app.db import base as _base  # noqa: E402, F401
import app.db.models  # noqa: E402, F401 — registers all model classes

target_metadata = _base.Base.metadata

# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run in 'offline' mode — emit SQL to stdout without a live connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run in 'online' mode — connect and apply migrations directly."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # no pool for migration process
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
