from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.activity import (
    ActivityCategory,
    ActivityCreate,
    ActivityListResponse,
    ActivityResponse,
    ActivitySummaryResponse,
    ensure_timezone_aware,
)
from app.services.activity_service import (
    create_activity,
    get_activity_for_user,
    list_activities,
    summarize_activities_by_category,
)

router = APIRouter(prefix="/activities", tags=["activities"])


def _parse_optional_date_range(
    start_date: datetime | None,
    end_date: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    try:
        normalized_start = ensure_timezone_aware(start_date) if start_date else None
        normalized_end = ensure_timezone_aware(end_date) if end_date else None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if normalized_start and normalized_end and normalized_start > normalized_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_date must be earlier than or equal to end_date.",
        )
    return normalized_start, normalized_end


@router.post(
    "",
    response_model=ActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a new unified activity",
)
def record_activity(
    payload: ActivityCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivityResponse:
    """Create a validated activity record scoped to the authenticated user."""
    activity = create_activity(db, user_id=current_user.id, payload=payload)
    return ActivityResponse.model_validate(activity)


@router.get(
    "",
    response_model=ActivityListResponse,
    status_code=status.HTTP_200_OK,
    summary="List authenticated user's activities",
)
def read_activities(
    category: ActivityCategory | None = None,
    source: str | None = Query(default=None, min_length=1, max_length=128),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivityListResponse:
    """Retrieve paginated activities owned by the authenticated user."""
    cleaned_source: str | None = None
    if source is not None:
        cleaned_source = source.strip()
        if not cleaned_source:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="source query parameter cannot be blank.",
            )

    normalized_start, normalized_end = _parse_optional_date_range(start_date, end_date)
    items, total = list_activities(
        db,
        user_id=current_user.id,
        category=category.value if category else None,
        source=cleaned_source,
        start_date=normalized_start,
        end_date=normalized_end,
        limit=limit,
        offset=offset,
    )
    return ActivityListResponse(
        items=[ActivityResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/summary",
    response_model=ActivitySummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Summarize activity counts by category",
)
def read_activity_summary(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivitySummaryResponse:
    """Return counts grouped by activity category for the authenticated user."""
    normalized_start, normalized_end = _parse_optional_date_range(start_date, end_date)
    by_category, total_count = summarize_activities_by_category(
        db,
        user_id=current_user.id,
        start_date=normalized_start,
        end_date=normalized_end,
    )
    return ActivitySummaryResponse(
        total_count=total_count,
        start_date=normalized_start,
        end_date=normalized_end,
        by_category=by_category,
    )


@router.get(
    "/{activity_id}",
    response_model=ActivityResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a single activity record",
)
def read_activity_by_id(
    activity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivityResponse:
    """Retrieve an activity record only if it belongs to the authenticated user."""
    activity = get_activity_for_user(
        db,
        user_id=current_user.id,
        activity_id=activity_id,
    )
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity record not found.",
        )
    return ActivityResponse.model_validate(activity)
