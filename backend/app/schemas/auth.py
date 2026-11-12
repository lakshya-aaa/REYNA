from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _normalize_email(value: str) -> str:
    return value.strip().lower()


class SetupRequest(BaseModel):
    """Payload to register REYNA's initial user account.

    Note: The bootstrap token must be supplied via request headers
    (`Authorization: Bearer <token>` or `X-Bootstrap-Token`), never in the JSON body.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128, repr=False)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        if isinstance(value, str):
            return _normalize_email(value)
        return value

    @field_validator("password")
    @classmethod
    def reject_blank_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password cannot be blank or whitespace only.")
        return value


class LoginRequest(BaseModel):
    """Payload to authenticate an existing REYNA user."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128, repr=False)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        if isinstance(value, str):
            return _normalize_email(value)
        return value


class UserResponse(BaseModel):
    """Public representation of a REYNA user (never includes password hashes)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    """JWT access token response returned after successful login."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
