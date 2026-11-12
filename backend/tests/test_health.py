from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.core.config import BACKEND_DIR, Settings, get_settings, normalize_database_url
from app.db.session import get_db, resolve_runtime_database_url
from app.main import create_app


def test_health_endpoints_return_ok_and_security_headers(client: TestClient) -> None:
    root_resp = client.get("/health")
    assert root_resp.status_code == 200
    assert root_resp.json() == {"status": "ok", "database": "connected"}
    assert root_resp.headers.get("x-content-type-options") == "nosniff"
    assert root_resp.headers.get("x-frame-options") == "DENY"

    v1_resp = client.get("/api/v1/health")
    assert v1_resp.status_code == 200
    assert v1_resp.json() == {"status": "ok", "database": "connected"}
    assert v1_resp.headers.get("cache-control") == "no-store"


def test_health_returns_503_without_leaking_secrets_when_db_fails(
    client: TestClient,
) -> None:
    class BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("postgresql://secret_user:secret_pass@internal-host:5432/db")

    def override_broken_db():
        yield BrokenSession()

    client.app.dependency_overrides[get_db] = override_broken_db
    try:
        resp = client.get("/api/v1/health")
    finally:
        client.app.dependency_overrides.clear()

    assert resp.status_code == 503
    body = resp.json()
    assert body == {"status": "degraded", "database": "unavailable"}
    assert "secret_pass" not in resp.text
    assert "internal-host" not in resp.text


def test_unhandled_exception_returns_safe_500_without_leaking_details(
    test_settings: Settings,
) -> None:
    app = create_app(test_settings)

    def override_exploding_db():
        raise RuntimeError("postgresql://admin:TopSecretDBPass@private-db:5432/reyna")

    app.dependency_overrides[get_db] = override_exploding_db
    with TestClient(app, raise_server_exceptions=False) as safe_client:
        resp = safe_client.get("/api/v1/health")

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error."}
    assert "TopSecretDBPass" not in resp.text
    assert "private-db" not in resp.text


def test_startup_rejects_placeholder_or_missing_secret(tmp_path: Path) -> None:
    db_url = f"sqlite:///{(tmp_path / 'startup.db').as_posix()}"
    bad_settings = Settings(
        _env_file=None,
        ENVIRONMENT="development",
        SECRET_KEY="replace-with-a-long-random-secret-key-at-least-32-chars",
        DATABASE_URL=db_url,
        TEST_DATABASE_URL=db_url,
    )
    app = create_app(bad_settings)
    with pytest.raises(ValueError, match="SECRET_KEY"):
        with TestClient(app):
            pass


def test_startup_rejects_placeholder_or_short_bootstrap_token_but_allows_empty(
    tmp_path: Path,
) -> None:
    db_url = f"sqlite:///{(tmp_path / 'bootstrap.db').as_posix()}"
    for bad_bootstrap in ("replace-with-a-one-time-bootstrap-token", "short-token"):
        bad_settings = Settings(
            _env_file=None,
            ENVIRONMENT="development",
            SECRET_KEY="valid-secret-key-at-least-32-chars-long",
            REYNA_BOOTSTRAP_TOKEN=bad_bootstrap,
            DATABASE_URL=db_url,
            TEST_DATABASE_URL=db_url,
        )
        with pytest.raises(ValueError, match="REYNA_BOOTSTRAP_TOKEN"):
            bad_settings.validate_runtime_secrets()

    post_setup_settings = Settings(
        _env_file=None,
        ENVIRONMENT="development",
        SECRET_KEY="valid-secret-key-at-least-32-chars-long",
        REYNA_BOOTSTRAP_TOKEN="",
        DATABASE_URL=db_url,
        TEST_DATABASE_URL=db_url,
    )
    post_setup_settings.validate_runtime_secrets()


def test_production_forbids_missing_db_sqlite_wildcard_cors_and_unsafe_jwt_alg() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL must be configured"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="a" * 40,
            DATABASE_URL="",
            DIRECT_URL="postgresql://user:pass@host:5432/reyna",
        )

    secret_db_url = "postgresql://neondb_owner:TopSecretNeonPw987@ep-test-pooler.neon.tech:5432/reyna"
    with pytest.raises(ValidationError, match="DIRECT_URL must be configured") as exc_info:
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="a" * 40,
            DATABASE_URL=secret_db_url,
            DIRECT_URL="",
        )
    assert "TopSecretNeonPw987" not in str(exc_info.value)
    assert "ep-test-pooler" not in str(exc_info.value)

    with pytest.raises(ValidationError, match="SQLite is not permitted as DIRECT_URL"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="a" * 40,
            DATABASE_URL="postgresql://user:pass@ep-test-pooler.neon.tech:5432/reyna",
            DIRECT_URL="sqlite:///./prod.db",
        )

    with pytest.raises(ValidationError, match="SQLite is not permitted"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="a" * 40,
            DATABASE_URL="sqlite:///./prod.db",
            DIRECT_URL="postgresql://user:pass@host:5432/reyna",
        )

    with pytest.raises(ValidationError, match="Wildcard CORS"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="a" * 40,
            DATABASE_URL="postgresql://user:pass@host:5432/reyna",
            DIRECT_URL="postgresql://user:pass@host:5432/reyna",
            CORS_ORIGINS="*",
        )

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="a" * 40,
            JWT_ALGORITHM="none",
            DATABASE_URL="postgresql://user:pass@host:5432/reyna",
            DIRECT_URL="postgresql://user:pass@host:5432/reyna",
        )


def test_database_url_normalization_supports_render_postgres_urls() -> None:
    assert (
        normalize_database_url("postgres://u:p@host:5432/db")
        == "postgresql+psycopg://u:p@host:5432/db"
    )
    assert (
        normalize_database_url("postgresql://u:p@host:5432/db")
        == "postgresql+psycopg://u:p@host:5432/db"
    )
    assert (
        normalize_database_url("postgresql+psycopg://u:p@host:5432/db")
        == "postgresql+psycopg://u:p@host:5432/db"
    )


def test_cors_allows_configured_origin_and_blocks_unknown_origin(client: TestClient) -> None:
    allowed = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"

    blocked = client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert blocked.headers.get("access-control-allow-origin") is None


def test_pg8000_fallback_handles_neon_ssl_and_channel_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    neon_url = (
        "postgresql://neondb_owner:pw@ep-cool-pooler.us-east-2.aws.neon.tech/"
        "neondb?sslmode=require&channel_binding=require"
    )
    normalized = normalize_database_url(neon_url)
    assert normalized.startswith("postgresql+psycopg://")
    assert "sslmode=require" in normalized
    assert "channel_binding=require" in normalized

    # When psycopg is loadable (Render Linux), keep Neon URL query params intact
    monkeypatch.setattr("app.db.session._is_psycopg_loadable", lambda: True)
    psycopg_url, psycopg_args = resolve_runtime_database_url(normalized)
    assert psycopg_url == normalized
    assert psycopg_args == {}

    # When psycopg cannot load (e.g. restricted Windows), adapt cleanly for pg8000 + SSL
    monkeypatch.setattr("app.db.session._is_psycopg_loadable", lambda: False)
    runtime_url, connect_args = resolve_runtime_database_url(normalized)
    assert runtime_url == (
        "postgresql+pg8000://neondb_owner:pw@ep-cool-pooler.us-east-2.aws.neon.tech/neondb"
    )
    assert "ssl_context" in connect_args

    # sslmode=disable must not force ssl_context
    disabled_url, disabled_args = resolve_runtime_database_url(
        "postgresql+pg8000://u:p@localhost:5432/reyna?sslmode=disable"
    )
    assert disabled_url == "postgresql+pg8000://u:p@localhost:5432/reyna"
    assert "ssl_context" not in disabled_args


def test_render_yaml_uses_free_web_service_and_external_db_without_secrets() -> None:
    render_yaml_path = Path(__file__).resolve().parents[2] / "render.yaml"
    content = render_yaml_path.read_text(encoding="utf-8")

    assert "plan: free" in content
    assert "databases:" not in content
    assert "fromDatabase:" not in content
    assert "preDeployCommand:" not in content
    assert "alembic upgrade head && uvicorn app.main:app" in content
    assert "neon.tech" not in content
    assert "DATABASE_URL" in content
    assert "DIRECT_URL" in content
    assert "sync: false" in content


def test_app_uses_pooled_database_url_and_alembic_uses_direct_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pooled_url = (
        "postgresql://neondb_owner:pw@ep-test-123456-pooler.us-east-2.aws.neon.tech/"
        "neondb?sslmode=require&channel_binding=require"
    )
    direct_url = (
        "postgresql://neondb_owner:pw@ep-test-123456.us-east-2.aws.neon.tech/"
        "neondb?sslmode=require&channel_binding=require"
    )
    prod_settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="p" * 40,
        DATABASE_URL=pooled_url,
        DIRECT_URL=direct_url,
    )
    assert "-pooler." in prod_settings.effective_database_url
    assert "-pooler." not in prod_settings.migration_database_url
    assert prod_settings.effective_database_url.startswith("postgresql+psycopg://")
    assert prod_settings.migration_database_url.startswith("postgresql+psycopg://")

    # Verify real Alembic execution resolves DIRECT_URL (not pooled DATABASE_URL)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "p" * 40)
    monkeypatch.setenv("DATABASE_URL", pooled_url)
    monkeypatch.setenv("DIRECT_URL", direct_url)
    get_settings.cache_clear()

    captured_urls: list[str] = []
    original_configure = EnvironmentContext.configure

    def spy_configure(self, *args, **kwargs):
        if "url" in kwargs and kwargs["url"] is not None:
            captured_urls.append(str(kwargs["url"]))
        return original_configure(self, *args, **kwargs)

    monkeypatch.setattr(EnvironmentContext, "configure", spy_configure)
    try:
        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        alembic_command.upgrade(alembic_cfg, "head", sql=True)
    finally:
        get_settings.cache_clear()

    assert len(captured_urls) == 1
    assert "-pooler." not in captured_urls[0]
    assert "ep-test-123456.us-east-2.aws.neon.tech" in captured_urls[0]


def test_migration_database_url_refuses_pooled_fallback_in_production() -> None:
    prod_settings = Settings.model_construct(
        ENVIRONMENT="production",
        DATABASE_URL=Settings.model_fields["DATABASE_URL"].annotation(
            "postgresql+psycopg://u:p@ep-test-pooler.neon.tech/neondb?sslmode=require"
        ),
        DIRECT_URL=Settings.model_fields["DIRECT_URL"].annotation(""),
        TEST_DATABASE_URL=Settings.model_fields["TEST_DATABASE_URL"].annotation(""),
    )
    with pytest.raises(ValueError, match="DIRECT_URL is required"):
        _ = prod_settings.migration_database_url


def test_sqlite_allowed_only_for_isolated_test_environment() -> None:
    test_env = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        SECRET_KEY="t" * 40,
        DATABASE_URL="",
        DIRECT_URL="",
        TEST_DATABASE_URL="sqlite:///./isolated_test.db",
    )
    assert test_env.effective_database_url == "sqlite:///./isolated_test.db"
    assert test_env.migration_database_url == "sqlite:///./isolated_test.db"


def test_no_hardcoded_database_credentials_in_app_or_config() -> None:
    repo_root = BACKEND_DIR.parent
    defaults = Settings(_env_file=None)
    assert defaults.DATABASE_URL.get_secret_value() == ""
    assert defaults.DIRECT_URL.get_secret_value() == ""
    assert defaults.SECRET_KEY.get_secret_value() == ""

    env_example = (repo_root / ".env.example").read_text(encoding="utf-8")
    assert "DATABASE_URL=postgresql://neondb_owner:replace_with_password@" in env_example
    assert "DIRECT_URL=postgresql://neondb_owner:replace_with_password@" in env_example
    assert "-pooler." in env_example

    for py_file in list((BACKEND_DIR / "app").rglob("*.py")) + list(
        (BACKEND_DIR / "migrations").rglob("*.py")
    ):
        text = py_file.read_text(encoding="utf-8")
        assert "neon.tech" not in text, f"Unexpected Neon hostname in {py_file}"
        assert "npg_" not in text, f"Unexpected Neon password prefix in {py_file}"


def test_docs_disabled_in_production_by_default() -> None:
    prod_settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="p" * 40,
        DATABASE_URL="postgresql://user:pass@host-pooler:5432/reyna",
        DIRECT_URL="postgresql://user:pass@host:5432/reyna",
    )
    assert prod_settings.docs_enabled is False
    prod_app = create_app(prod_settings)
    assert prod_app.docs_url is None
    assert prod_app.openapi_url is None
