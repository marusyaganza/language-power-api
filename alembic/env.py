# alembic/env.py
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import every module that defines models, so Base.metadata knows about them.
# Without these, autogenerate sees no tables and emits a migration that drops
# them all. Add new model modules here.
import games.models  # noqa: F401
import users.models  # noqa: F401
import words.models  # noqa: F401
from core.database import Base
from settings import settings

config = context.config

# override alembic.ini's URL with the one from your actual app settings,
# so migrations use the same async driver (postgresql+psycopg) as the app
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    # Keep loggers created before this point working: by default fileConfig
    # disables them, which silenced the app's warnings when migrations ran in
    # the same process (the API tests do).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout (`alembic upgrade --sql`) without connecting."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run the migrations on a sync connection; called through `run_sync`."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Connect with an async engine and run the migrations on it."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
