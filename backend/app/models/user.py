from datetime import datetime
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import Boolean, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TZDateTime, utcnow

if TYPE_CHECKING:
    from app.models.activity import Activity


class User(Base):
    """Represents a REYNA user account."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime,
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    activities: Mapped[list["Activity"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
