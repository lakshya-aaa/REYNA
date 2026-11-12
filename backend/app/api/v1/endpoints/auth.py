from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.dependencies import bearer_scheme, get_current_user
from app.core.rate_limit import enforce_rate_limit, extract_client_ip
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, SetupRequest, TokenResponse, UserResponse
from app.services.auth_service import (
    BootstrapNotConfiguredError,
    InvalidBootstrapTokenError,
    SetupAlreadyCompletedError,
    authenticate_user,
    create_initial_user,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _extract_header_bootstrap_token(
    credentials: HTTPAuthorizationCredentials | None,
    x_bootstrap_token: str | None,
) -> str | None:
    """Extract bootstrap token strictly from headers (Authorization Bearer preferred)."""
    bearer_token: str | None = None
    if credentials is not None:
        if credentials.scheme.lower() != "bearer" or not credentials.credentials.strip():
            return None
        bearer_token = credentials.credentials.strip()

    header_token = x_bootstrap_token.strip() if x_bootstrap_token and x_bootstrap_token.strip() else None

    if bearer_token and header_token and bearer_token != header_token:
        return None
    return bearer_token or header_token


@router.post(
    "/setup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register the first REYNA account",
)
def setup_initial_account(
    request: Request,
    payload: SetupRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    """Create the initial account only when no accounts exist and bootstrap token matches.

    Supply the one-time token strictly via request headers (`Authorization: Bearer <token>`
    preferred, or `X-Bootstrap-Token`). Once an account exists, this endpoint is
    permanently disabled.
    """
    if settings.RATE_LIMIT_ENABLED:
        client_ip = extract_client_ip(request)
        enforce_rate_limit(
            request.app.state.rate_limiter,
            keys=["setup:global", f"setup:ip:{client_ip}"],
            max_requests=settings.AUTH_SETUP_RATE_LIMIT,
            window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
            detail="Too many setup attempts. Please wait before trying again.",
        )

    provided_token = _extract_header_bootstrap_token(credentials, x_bootstrap_token)
    try:
        user = create_initial_user(
            db,
            email=payload.email,
            password=payload.password,
            provided_bootstrap_token=provided_token,
            settings=settings,
        )
    except SetupAlreadyCompletedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except BootstrapNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except InvalidBootstrapTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and obtain a JWT access token",
)
def login(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Verify email and password, returning a short-lived Bearer JWT token."""
    if settings.RATE_LIMIT_ENABLED:
        client_ip = extract_client_ip(request)
        enforce_rate_limit(
            request.app.state.rate_limiter,
            keys=[f"login:ip:{client_ip}", f"login:email:{payload.email}"],
            max_requests=settings.AUTH_LOGIN_RATE_LIMIT,
            window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
            detail="Too many login attempts. Please wait before trying again.",
        )

    user = authenticate_user(db, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, expires_at = create_access_token(str(user.id), settings)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_at=expires_at,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the currently authenticated user",
)
def read_current_user(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return profile metadata for the authenticated user."""
    return UserResponse.model_validate(current_user)
