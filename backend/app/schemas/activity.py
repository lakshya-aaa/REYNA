from datetime import datetime, timezone
from enum import StrEnum
import json
import re
from typing import Any
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

_OFFSET_TZ_PATTERN = re.compile(r"^[+-](?:[01]\d|2[0-3]):[0-5]\d$")
MAX_DETAILS_BYTES = 65536


class ActivityCategory(StrEnum):
    """Initial supported REYNA activity categories."""

    SMARTPHONE = "smartphone"
    LAPTOP = "laptop"
    FITNESS = "fitness"
    HEALTH = "health"
    READING = "reading"
    LEARNING = "learning"
    DEVELOPMENT = "development"
    ACADEMICS = "academics"
    CALENDAR = "calendar"
    PERSONAL = "personal"


class ActivityStatus(StrEnum):
    """Lifecycle certainty status of an activity record."""

    CONFIRMED = "confirmed"
    DETECTED = "detected"
    SCHEDULED = "scheduled"
    MANUALLY_ENTERED = "manually_entered"
    ESTIMATED = "estimated"


def ensure_timezone_aware(value: datetime) -> datetime:
    """Validate that a datetime includes timezone information and normalize to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            "Timestamp must be timezone-aware (include 'Z' or an offset like '+05:30')."
        )
    return value.astimezone(timezone.utc)


def validate_timezone_identifier(value: str) -> str:
    """Validate an IANA timezone name (e.g. 'Asia/Kolkata', 'UTC') or fixed UTC offset."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Timezone cannot be empty.")
    if cleaned.upper() == "Z" or cleaned.upper() == "UTC":
        return "UTC"
    if _OFFSET_TZ_PATTERN.match(cleaned):
        return cleaned
    try:
        ZoneInfo(cleaned)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"Unknown timezone '{cleaned}'. Use an IANA timezone like 'UTC' or 'Asia/Kolkata'."
        ) from exc
    return cleaned


class ActivityCreate(BaseModel):
    """Payload to record a new unified activity event."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    category: ActivityCategory
    source: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    details: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: ActivityStatus = ActivityStatus.MANUALLY_ENTERED

    @field_validator("source", "title")
    @classmethod
    def strip_non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be empty or whitespace only.")
        return stripped

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        return ensure_timezone_aware(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return validate_timezone_identifier(value)

    @field_validator("details")
    @classmethod
    def validate_details_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_DETAILS_BYTES:
            raise ValueError(f"details payload cannot exceed {MAX_DETAILS_BYTES} bytes.")
        return value


class ActivityResponse(BaseModel):
    """Serialized activity record returned to its authenticated owner."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    category: str
    source: str
    title: str
    details: dict[str, Any]
    occurred_at: datetime
    recorded_at: datetime
    timezone: str
    confidence: float | None
    status: str
    created_at: datetime


class ActivityListResponse(BaseModel):
    """Paginated list of user-owned activity records."""

    items: list[ActivityResponse]
    total: int
    limit: int
    offset: int


class ActivitySummaryResponse(BaseModel):
    """Activity counts grouped by category for an optional date range."""

    total_count: int
    start_date: datetime | None
    end_date: datetime | None
    by_category: dict[str, int]
