from functools import lru_cache
import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = Path(__file__).resolve().parents[3]

_PLACEHOLDER_PREFIXES = (
    "replace-with",
    "your-",
    "changeme",
    "example",
)

MIN_SECRET_KEY_LENGTH = 32
MIN_BOOTSTRAP_TOKEN_LENGTH = 24


def normalize_database_url(raw_url: str) -> str:
    """Normalize PostgreSQL URLs for SQLAlchemy 2 + psycopg3."""
    url = raw_url.strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def looks_like_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return any(lowered.startswith(prefix) for prefix in _PLACEHOLDER_PREFIXES)


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env files."""

    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        hide_input_in_errors=True,
    )

    APP_NAME: str = "REYNA"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    ENABLE_DOCS: bool | None = None
    LOG_LEVEL: str = "INFO"

    SECRET_KEY: SecretStr = SecretStr("")
    JWT_ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=10080)

    REYNA_BOOTSTRAP_TOKEN: SecretStr = SecretStr("")

    RATE_LIMIT_ENABLED: bool = True
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, ge=10, le=3600)
    AUTH_LOGIN_RATE_LIMIT: int = Field(default=10, ge=1, le=500)
    AUTH_SETUP_RATE_LIMIT: int = Field(default=5, ge=1, le=100)

    DATABASE_URL: SecretStr = SecretStr("")
    DIRECT_URL: SecretStr = SecretStr("")
    TEST_DATABASE_URL: SecretStr = SecretStr("sqlite:///./test_reyna.db")

    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("CORS_ORIGINS JSON must be a list of origin strings.")
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        raise ValueError("CORS_ORIGINS must be a comma-separated string or list of origins.")

    @field_validator("DATABASE_URL", "DIRECT_URL", "TEST_DATABASE_URL", mode="before")
    @classmethod
    def normalize_db_secret(cls, value: Any) -> Any:
        if isinstance(value, SecretStr):
            return SecretStr(normalize_database_url(value.get_secret_value()))
        if isinstance(value, str):
            return normalize_database_url(value)
        return value

    @model_validator(mode="after")
    def validate_environment_rules(self) -> "Settings":
        db_url = self.DATABASE_URL.get_secret_value().strip()
        direct_url = self.DIRECT_URL.get_secret_value().strip()
        if self.ENVIRONMENT == "production":
            if not db_url:
                raise ValueError("DATABASE_URL must be configured in production.")
            if db_url.startswith("sqlite"):
                raise ValueError("SQLite is not permitted as the database in production.")
            if not direct_url:
                raise ValueError(
                    "DIRECT_URL must be configured in production for database migrations."
                )
            if direct_url.startswith("sqlite"):
                raise ValueError("SQLite is not permitted as DIRECT_URL in production.")
            if "*" in self.CORS_ORIGINS:
                raise ValueError("Wildcard CORS origin '*' is not permitted in production.")
        return self

    @property
    def docs_enabled(self) -> bool:
        if self.ENABLE_DOCS is not None:
            return self.ENABLE_DOCS
        return self.ENVIRONMENT != "production"

    @property
    def effective_database_url(self) -> str:
        """Database URL used by the FastAPI application runtime (pooled in production)."""
        if self.ENVIRONMENT == "test":
            test_url = self.TEST_DATABASE_URL.get_secret_value().strip()
            if test_url:
                return test_url
        return self.DATABASE_URL.get_secret_value().strip()

    @property
    def migration_database_url(self) -> str:
        """Database URL used by Alembic migrations (prefers DIRECT_URL)."""
        if self.ENVIRONMENT == "test":
            test_url = self.TEST_DATABASE_URL.get_secret_value().strip()
            if test_url:
                return test_url

        direct_url = self.DIRECT_URL.get_secret_value().strip()
        if direct_url:
            return direct_url

        if self.ENVIRONMENT == "production":
            raise ValueError(
                "DIRECT_URL is required for migrations in production; "
                "refusing to fall back to pooled DATABASE_URL."
            )

        return self.DATABASE_URL.get_secret_value().strip()

    def validate_runtime_secrets(self) -> None:
        """Validate critical security settings when starting the API server."""
        secret = self.SECRET_KEY.get_secret_value().strip()
        if not secret or looks_like_placeholder(secret):
            raise ValueError(
                "SECRET_KEY is missing or still set to a placeholder. "
                "Generate a strong random secret and configure SECRET_KEY in your environment."
            )
        if len(secret) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters long."
            )

        bootstrap_token = self.REYNA_BOOTSTRAP_TOKEN.get_secret_value().strip()
        if bootstrap_token:
            if looks_like_placeholder(bootstrap_token):
                raise ValueError(
                    "REYNA_BOOTSTRAP_TOKEN is still set to a placeholder value. "
                    "Replace it with a strong random token or clear it after setup completes."
                )
            if len(bootstrap_token) < MIN_BOOTSTRAP_TOKEN_LENGTH:
                raise ValueError(
                    f"REYNA_BOOTSTRAP_TOKEN must be at least {MIN_BOOTSTRAP_TOKEN_LENGTH} characters long."
                )

        db_url = self.effective_database_url
        if not db_url:
            raise ValueError(
                "DATABASE_URL is not configured. Set DATABASE_URL to your PostgreSQL connection string."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
