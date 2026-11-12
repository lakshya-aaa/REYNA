from datetime import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.activity import Activity
from app.schemas.activity import ActivityCreate


def create_activity(
    db: Session,
    *,
    user_id: uuid.UUID,
    payload: ActivityCreate,
) -> Activity:
    """Create and persist a user-scoped activity record."""
    activity = Activity(
        user_id=user_id,
        category=payload.category.value,
        source=payload.source,
        title=payload.title,
        details=payload.details,
        occurred_at=payload.occurred_at,
        recorded_at=utcnow(),
        timezone=payload.timezone,
        confidence=payload.confidence,
        status=payload.status.value,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


def list_activities(
    db: Session,
    *,
    user_id: uuid.UUID,
    category: str | None = None,
    source: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Activity], int]:
    """Return paginated activity records strictly scoped to the given user."""
    filters = [Activity.user_id == user_id]

    if category is not None:
        filters.append(Activity.category == category)
    if source is not None:
        filters.append(Activity.source == source.strip())
    if start_date is not None:
        filters.append(Activity.occurred_at >= start_date)
    if end_date is not None:
        filters.append(Activity.occurred_at <= end_date)

    total = db.scalar(select(func.count(Activity.id)).where(*filters)) or 0
    items = list(
        db.scalars(
            select(Activity)
            .where(*filters)
            .order_by(Activity.occurred_at.desc(), Activity.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return items, total


def get_activity_for_user(
    db: Session,
    *,
    user_id: uuid.UUID,
    activity_id: uuid.UUID,
) -> Activity | None:
    """Fetch a single activity only if it belongs to the authenticated user."""
    return db.scalar(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.user_id == user_id,
        )
    )


def summarize_activities_by_category(
    db: Session,
    *,
    user_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> tuple[dict[str, int], int]:
    """Return activity counts grouped by category strictly scoped to the given user."""
    filters = [Activity.user_id == user_id]
    if start_date is not None:
        filters.append(Activity.occurred_at >= start_date)
    if end_date is not None:
        filters.append(Activity.occurred_at <= end_date)

    rows = db.execute(
        select(Activity.category, func.count(Activity.id))
        .where(*filters)
        .group_by(Activity.category)
        .order_by(Activity.category)
    ).all()

    by_category = {str(category): int(count) for category, count in rows}
    total_count = sum(by_category.values())
    return by_category, total_count
