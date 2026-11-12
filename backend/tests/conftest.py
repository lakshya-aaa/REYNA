from collections.abc import Generator
from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.db.session import init_db_session, reset_db_session
from app.main import create_app
from app.models.user import User

TEST_SECRET_KEY = "test-secret-key-at-least-32-characters-long-123456"
TEST_BOOTSTRAP_TOKEN = "test-bootstrap-token-reyna-phase1"


def run_alembic_upgrade(database_url: str) -> None:
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture()
def test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    db_file = tmp_path / f"test_{uuid.uuid4().hex}.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.setenv("REYNA_BOOTSTRAP_TOKEN", TEST_BOOTSTRAP_TOKEN)
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("TEST_DATABASE_URL", db_url)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")

    get_settings.cache_clear()
    reset_db_session()
    run_alembic_upgrade(db_url)
    return get_settings()


@pytest.fixture()
def client(test_settings: Settings) -> Generator[TestClient, None, None]:
    application = create_app(test_settings)
    with TestClient(application) as test_client:
        yield test_client
    reset_db_session()
    get_settings.cache_clear()


@pytest.fixture()
def db_session(client: TestClient, test_settings: Settings) -> Generator[Session, None, None]:
    _, session_factory = init_db_session(test_settings)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def create_user_in_db(db_session: Session, test_settings: Settings):
    """Helper factory to insert users and issue tokens for isolation tests."""

    def _create(
        *,
        email: str,
        password: str = "StrongTestPassword123!",
        is_active: bool = True,
    ) -> tuple[User, str]:
        user = User(
            email=email.strip().lower(),
            hashed_password=hash_password(password),
            is_active=is_active,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        token, _ = create_access_token(str(user.id), test_settings)
        return user, token

    return _create
