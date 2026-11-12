from collections.abc import Generator
import ssl
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import Engine, NullPool, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def _is_psycopg_loadable() -> bool:
    """Return True if psycopg3 can load a C, binary, or system libpq backend."""
    try:
        import psycopg  # noqa: F401

        return True
    except Exception:
        return False


def _adapt_url_for_pg8000(url: str) -> tuple[str, dict[str, Any]]:
    """Translate libpq-style query parameters (e.g. Neon sslmode/channel_binding) for pg8000."""
    parsed = urlparse(url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))

    sslmode = query_items.pop("sslmode", None)
    for libpq_only in (
        "channel_binding",
        "sslrootcert",
        "sslcert",
        "sslkey",
        "target_session_attrs",
    ):
        query_items.pop(libpq_only, None)

    connect_timeout = query_items.pop("connect_timeout", None)
    cleaned_url = urlunparse(parsed._replace(query=urlencode(query_items)))

    connect_args: dict[str, Any] = {}
    if sslmode and sslmode.lower() in {"require", "verify-ca", "verify-full"}:
        connect_args["ssl_context"] = ssl.create_default_context()
    if connect_timeout and connect_timeout.isdigit():
        connect_args["timeout"] = int(connect_timeout)

    return cleaned_url, connect_args


def resolve_runtime_database_url(database_url: str) -> tuple[str, dict[str, Any]]:
    """Resolve the active PostgreSQL driver URL and any driver-specific connect_args.

    Prefers psycopg3 when loadable (e.g., on Linux/Render). Falls back to pure-Python
    pg8000 when psycopg cannot load libpq/binary extensions (such as restricted Windows
    Application Control environments).
    """
    if database_url.startswith("postgresql+psycopg://") and not _is_psycopg_loadable():
        fallback_url = "postgresql+pg8000://" + database_url[len("postgresql+psycopg://") :]
        return _adapt_url_for_pg8000(fallback_url)

    if database_url.startswith("postgresql+pg8000://"):
        return _adapt_url_for_pg8000(database_url)

    return database_url, {}


def create_db_engine(database_url: str, *, use_null_pool: bool = False) -> Engine:
    """Create a SQLAlchemy engine appropriate for the configured database dialect."""
    if not database_url:
        raise ValueError("Database URL cannot be empty.")

    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            future=True,
        )

    runtime_url, connect_args = resolve_runtime_database_url(database_url)
    if use_null_pool:
        return create_engine(
            runtime_url,
            connect_args=connect_args,
            poolclass=NullPool,
            future=True,
        )

    return create_engine(
        runtime_url,
        connect_args=connect_args,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
        pool_pre_ping=True,
        future=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a configured SQLAlchemy session factory."""
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def init_db_session(settings: Settings | None = None) -> tuple[Engine, sessionmaker[Session]]:
    """Initialize or return the active engine and session factory."""
    global _engine, _session_factory
    if _engine is None or _session_factory is None:
        resolved_settings = settings or get_settings()
        _engine = create_db_engine(resolved_settings.effective_database_url)
        _session_factory = create_session_factory(_engine)
    return _engine, _session_factory


def reset_db_session() -> None:
    """Dispose the cached engine and clear the session factory (useful in tests)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped database session per request."""
    _, session_factory = init_db_session()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def check_database_health(db: Session) -> bool:
    """Execute a lightweight connectivity query without exposing details."""
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
