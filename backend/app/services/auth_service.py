import threading

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import (
    MIN_BOOTSTRAP_TOKEN_LENGTH,
    Settings,
    looks_like_placeholder,
)
from app.core.security import (
    hash_password,
    password_needs_rehash,
    verify_bootstrap_token,
    verify_password,
)
from app.models.user import User

_POSTGRES_SETUP_LOCK_ID = 723961
_NON_PG_SETUP_LOCK = threading.Lock()
_DUMMY_ARGON2_HASH = hash_password("reyna-constant-time-login-guard")


class SetupAlreadyCompletedError(Exception):
    """Raised when initial account setup is attempted after a user already exists."""


class BootstrapNotConfiguredError(Exception):
    """Raised when REYNA_BOOTSTRAP_TOKEN is missing, placeholder, or too short."""


class InvalidBootstrapTokenError(Exception):
    """Raised when the provided bootstrap token does not match."""


def has_any_user(db: Session) -> bool:
    """Return True if at least one user account already exists."""
    return db.scalar(select(User.id).limit(1)) is not None


def _create_initial_user_locked(
    db: Session,
    *,
    email: str,
    password: str,
    provided_bootstrap_token: str | None,
    settings: Settings,
) -> User:
    if has_any_user(db):
        raise SetupAlreadyCompletedError(
            "Initial setup has already been completed and is permanently disabled."
        )

    expected_token = settings.REYNA_BOOTSTRAP_TOKEN.get_secret_value().strip()
    if (
        not expected_token
        or looks_like_placeholder(expected_token)
        or len(expected_token) < MIN_BOOTSTRAP_TOKEN_LENGTH
    ):
        raise BootstrapNotConfiguredError(
            "Initial setup is disabled because REYNA_BOOTSTRAP_TOKEN is not safely configured."
        )

    if not provided_bootstrap_token or not verify_bootstrap_token(
        provided_bootstrap_token.strip(), expected_token
    ):
        raise InvalidBootstrapTokenError("Invalid bootstrap token.")

    user = User(
        email=email.strip().lower(),
        hashed_password=hash_password(password),
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SetupAlreadyCompletedError(
            "Initial setup has already been completed and is permanently disabled."
        ) from exc

    db.refresh(user)
    return user


def create_initial_user(
    db: Session,
    *,
    email: str,
    password: str,
    provided_bootstrap_token: str | None,
    settings: Settings,
) -> User:
    """Create REYNA's first account only when zero accounts exist and bootstrap token matches."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _POSTGRES_SETUP_LOCK_ID},
        )
        return _create_initial_user_locked(
            db,
            email=email,
            password=password,
            provided_bootstrap_token=provided_bootstrap_token,
            settings=settings,
        )

    with _NON_PG_SETUP_LOCK:
        return _create_initial_user_locked(
            db,
            email=email,
            password=password,
            provided_bootstrap_token=provided_bootstrap_token,
            settings=settings,
        )


def authenticate_user(db: Session, *, email: str, password: str) -> User | None:
    """Verify email and password for an active user with timing-attack mitigation."""
    normalized_email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None or not user.is_active:
        # Run Argon2 verification against a dummy hash so timing does not leak account existence.
        verify_password(password, _DUMMY_ARGON2_HASH)
        return None

    if not verify_password(password, user.hashed_password):
        return None

    if password_needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(password)
        db.commit()
        db.refresh(user)

    return user
