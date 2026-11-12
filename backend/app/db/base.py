from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class TZDateTime(TypeDecorator[datetime]):
    """Store timezone-aware UTC datetimes across PostgreSQL and SQLite.

    PostgreSQL natively stores TIMESTAMPTZ values, while SQLite strips tzinfo on
    readback. This decorator enforces timezone-aware inputs and guarantees UTC
    timezone-aware datetime objects when reading rows back.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime values stored in REYNA must be timezone-aware.")
        return value.astimezone(timezone.utc)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    """Base declarative class for all REYNA SQLAlchemy models."""
