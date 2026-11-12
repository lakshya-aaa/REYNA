from datetime import datetime
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TZDateTime, utcnow

if TYPE_CHECKING:
    from app.models.user import User


class Activity(Base):
    """Unified activity record belonging to a single authenticated REYNA user."""

    __tablename__ = "activities"
    __table_args__ = (
        Index("ix_activities_user_occurred_at", "user_id", "occurred_at"),
        Index("ix_activities_user_category", "user_id", "category"),
        Index("ix_activities_user_source", "user_id", "source"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_activities_confidence_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Stored as VARCHAR rather than a database ENUM so new categories can be
    # introduced in application code without destructive schema migrations.
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        TZDateTime,
        nullable=False,
        index=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        TZDateTime,
        default=utcnow,
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime,
        default=utcnow,
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="activities")
