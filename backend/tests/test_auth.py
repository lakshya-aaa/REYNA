from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import logging

from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import create_access_token
from app.models.user import User
from tests.conftest import TEST_BOOTSTRAP_TOKEN, TEST_SECRET_KEY


def test_first_account_setup_requires_valid_bootstrap_token(client: TestClient) -> None:
    missing_token = client.post(
        "/api/v1/auth/setup",
        json={"email": "owner@example.com", "password": "VeryStrongPassword123!"},
    )
    assert missing_token.status_code == 403

    wrong_token = client.post(
        "/api/v1/auth/setup",
        headers={"X-Bootstrap-Token": "wrong-token"},
        json={"email": "owner@example.com", "password": "VeryStrongPassword123!"},
    )
    assert wrong_token.status_code == 403


def test_setup_rejects_bootstrap_token_in_request_body(client: TestClient) -> None:
    body_token = client.post(
        "/api/v1/auth/setup",
        json={
            "email": "owner@example.com",
            "password": "VeryStrongPassword123!",
            "bootstrap_token": TEST_BOOTSTRAP_TOKEN,
        },
    )
    assert body_token.status_code == 422


def test_setup_rejects_mismatched_authorization_and_bootstrap_headers(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/v1/auth/setup",
        headers={
            "Authorization": f"Bearer {TEST_BOOTSTRAP_TOKEN}",
            "X-Bootstrap-Token": "different-token-value-123456",
        },
        json={"email": "owner@example.com", "password": "VeryStrongPassword123!"},
    )
    assert resp.status_code == 403


def test_first_account_setup_succeeds_and_blocks_second_setup(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        "/api/v1/auth/setup",
        headers={"X-Bootstrap-Token": TEST_BOOTSTRAP_TOKEN},
        json={"email": "  Owner@EXAMPLE.com ", "password": "VeryStrongPassword123!"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "owner@example.com"
    assert data["is_active"] is True
    assert "hashed_password" not in data
    assert "password" not in data

    # Verify Argon2id hash stored in database
    user = db_session.scalar(select(User).where(User.email == "owner@example.com"))
    assert user is not None
    assert user.hashed_password.startswith("$argon2id$")

    # Second setup attempt must be permanently blocked even with valid bootstrap token
    second_attempt = client.post(
        "/api/v1/auth/setup",
        headers={"Authorization": f"Bearer {TEST_BOOTSTRAP_TOKEN}"},
        json={"email": "second@example.com", "password": "AnotherStrongPassword123!"},
    )
    assert second_attempt.status_code == 403
    assert "permanently disabled" in second_attempt.json()["detail"].lower()


def test_concurrent_setup_requests_only_create_one_account(
    client: TestClient,
    db_session: Session,
) -> None:
    def _attempt(index: int) -> int:
        resp = client.post(
            "/api/v1/auth/setup",
            headers={"Authorization": f"Bearer {TEST_BOOTSTRAP_TOKEN}"},
            json={
                "email": f"concurrent{index}@example.com",
                "password": "VeryStrongPassword123!",
            },
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(_attempt, range(4)))

    assert statuses.count(201) == 1
    assert statuses.count(403) == 3
    total_users = db_session.scalar(select(func.count(User.id)))
    assert total_users == 1


def test_setup_fails_if_bootstrap_token_missing_placeholder_or_short(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    for bad_token in ("", "replace-with-a-one-time-bootstrap-token", "too-short"):
        monkeypatch.setattr(
            test_settings,
            "REYNA_BOOTSTRAP_TOKEN",
            type(test_settings.REYNA_BOOTSTRAP_TOKEN)(bad_token),
        )
        response = client.post(
            "/api/v1/auth/setup",
            headers={"Authorization": f"Bearer {bad_token or 'anything'}"},
            json={"email": "owner@example.com", "password": "VeryStrongPassword123!"},
        )
        assert response.status_code == 503


def test_login_success_and_me_endpoint_with_bearer_setup(client: TestClient) -> None:
    setup_resp = client.post(
        "/api/v1/auth/setup",
        headers={"Authorization": f"Bearer {TEST_BOOTSTRAP_TOKEN}"},
        json={
            "email": "reyna.user@example.com",
            "password": "MySecurePassphrase!99",
        },
    )
    assert setup_resp.status_code == 201

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "REYNA.USER@example.com", "password": "MySecurePassphrase!99"},
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert token_data["token_type"] == "bearer"
    assert token_data["access_token"]
    assert token_data["expires_at"]

    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "reyna.user@example.com"


def test_login_rejects_wrong_password_unknown_email_and_inactive_user(
    client: TestClient,
    create_user_in_db,
) -> None:
    _, inactive_token = create_user_in_db(
        email="disabled@example.com",
        password="CorrectPassword123!",
        is_active=False,
    )
    create_user_in_db(email="owner@example.com", password="CorrectPassword123!")

    wrong_pw = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "WrongPassword123!"},
    )
    assert wrong_pw.status_code == 401

    unknown_user = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "CorrectPassword123!"},
    )
    assert unknown_user.status_code == 401

    inactive_login = client.post(
        "/api/v1/auth/login",
        json={"email": "disabled@example.com", "password": "CorrectPassword123!"},
    )
    assert inactive_login.status_code == 401

    inactive_me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {inactive_token}"},
    )
    assert inactive_me.status_code == 401


def test_protected_endpoints_reject_missing_invalid_tampered_and_expired_tokens(
    client: TestClient,
    create_user_in_db,
    test_settings: Settings,
) -> None:
    user, _ = create_user_in_db(email="authcheck@example.com")
    expired_token, _ = create_access_token(
        str(user.id),
        test_settings,
        expires_delta=timedelta(minutes=-5),
    )
    wrong_secret_token = jwt.encode(
        {
            "sub": str(user.id),
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            "type": "access",
        },
        "completely-different-secret-key-32-chars",
        algorithm="HS256",
    )
    wrong_type_token = jwt.encode(
        {
            "sub": str(user.id),
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            "type": "refresh",
        },
        TEST_SECRET_KEY,
        algorithm="HS256",
    )

    protected_calls = [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/activities"),
        ("GET", "/api/v1/activities/summary"),
        ("POST", "/api/v1/activities"),
    ]

    for method, path in protected_calls:
        assert client.request(method, path).status_code == 401
        for token in ("not.a.valid.jwt", expired_token, wrong_secret_token, wrong_type_token):
            resp = client.request(
                method,
                path,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 401


def test_rate_limiting_blocks_brute_force_on_setup_and_login(
    client: TestClient,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(test_settings, "AUTH_SETUP_RATE_LIMIT", 2)
    monkeypatch.setattr(test_settings, "AUTH_LOGIN_RATE_LIMIT", 3)

    # First 2 setup attempts hit normal 403 validation; 3rd is rate-limited (429)
    for _ in range(2):
        r = client.post(
            "/api/v1/auth/setup",
            headers={"Authorization": "Bearer invalid-bootstrap-token"},
            json={"email": "owner@example.com", "password": "StrongPassword123!"},
        )
        assert r.status_code == 403

    limited_setup = client.post(
        "/api/v1/auth/setup",
        headers={"Authorization": f"Bearer {TEST_BOOTSTRAP_TOKEN}"},
        json={"email": "owner@example.com", "password": "StrongPassword123!"},
    )
    assert limited_setup.status_code == 429
    assert "Retry-After" in limited_setup.headers

    # Even with rotating X-Forwarded-For IPs, email-based limit stops password brute force
    for idx in range(3):
        r = client.post(
            "/api/v1/auth/login",
            headers={"X-Forwarded-For": f"198.51.100.{idx + 1}"},
            json={"email": "victim@example.com", "password": "GuessPassword123!"},
        )
        assert r.status_code == 401

    limited_login = client.post(
        "/api/v1/auth/login",
        headers={"X-Forwarded-For": "198.51.100.99"},
        json={"email": "victim@example.com", "password": "GuessPassword123!"},
    )
    assert limited_login.status_code == 429
    assert "Retry-After" in limited_login.headers


def test_bootstrap_token_and_passwords_never_appear_in_logs(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_password = "SuperSecretUserPassword!98765"
    with caplog.at_level(logging.DEBUG):
        client.post(
            "/api/v1/auth/setup",
            headers={"Authorization": f"Bearer {TEST_BOOTSTRAP_TOKEN}"},
            json={"email": "logcheck@example.com", "password": secret_password},
        )
        client.post(
            "/api/v1/auth/login",
            json={"email": "logcheck@example.com", "password": secret_password},
        )
        client.post(
            "/api/v1/auth/login",
            json={"email": "logcheck@example.com", "password": "WrongPassword999!"},
        )

    assert secret_password not in caplog.text
    assert "WrongPassword999!" not in caplog.text
    assert TEST_BOOTSTRAP_TOKEN not in caplog.text
    assert TEST_SECRET_KEY not in caplog.text
