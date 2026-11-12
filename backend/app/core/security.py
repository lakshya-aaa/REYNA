from datetime import datetime, timedelta, timezone
import hmac
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
import jwt
from jwt import PyJWTError

from app.core.config import Settings

_password_hasher = PasswordHasher()


class TokenValidationError(Exception):
    """Raised when an access token is invalid, expired, or malformed."""


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored Argon2 hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def password_needs_rehash(hashed_password: str) -> bool:
    """Return True if the stored Argon2 hash parameters should be upgraded."""
    try:
        return _password_hasher.check_needs_rehash(hashed_password)
    except InvalidHashError:
        return False


def verify_bootstrap_token(provided_token: str, expected_token: str) -> bool:
    """Compare the provided bootstrap token against the configured token in constant time."""
    if not provided_token or not expected_token:
        return False
    return hmac.compare_digest(
        provided_token.encode("utf-8"),
        expected_token.encode("utf-8"),
    )


def create_access_token(
    subject: str,
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> tuple[str, datetime]:
    """Create a signed JWT access token and return (token, expires_at)."""
    secret = settings.SECRET_KEY.get_secret_value().strip()
    if not secret:
        raise RuntimeError("SECRET_KEY is not configured.")

    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        "type": "access",
    }
    token = jwt.encode(payload, secret, algorithm=settings.JWT_ALGORITHM)
    return token, expire


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Decode and validate a JWT access token."""
    secret = settings.SECRET_KEY.get_secret_value().strip()
    if not secret:
        raise RuntimeError("SECRET_KEY is not configured.")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except PyJWTError as exc:
        raise TokenValidationError("Invalid or expired access token.") from exc

    if payload.get("type") != "access" or not isinstance(payload.get("sub"), str):
        raise TokenValidationError("Invalid token payload.")

    return payload
