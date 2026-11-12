from logging.config import fileConfig

from alembic import context

from app.core.config import get_settings, normalize_database_url
from app.db.base import Base
from app.db.session import create_db_engine
import app.models  # noqa: F401 - ensure all models are registered on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Resolve the migration database URL (prefers DIRECT_URL over pooled DATABASE_URL)."""
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return normalize_database_url(configured_url)

    settings = get_settings()
    url = settings.migration_database_url
    if not url:
        raise RuntimeError(
            "No migration database URL configured for Alembic. "
            "Set DIRECT_URL (or DATABASE_URL in local development) in your environment."
        )
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without live DB connection)."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using a live database connection."""
    url = get_database_url()
    connectable = create_db_engine(url, use_null_pool=True)

    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
