from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient


from app.schemas.activity import ActivityCategory, MAX_DETAILS_BYTES


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_and_retrieve_activity_with_timezone_separation(
    client: TestClient,
    create_user_in_db,
) -> None:
    user, token = create_user_in_db(email="alice@example.com")

    payload = {
        "category": "development",
        "source": "vscode",
        "title": "Built REYNA backend authentication",
        "details": {"project": "REYNA", "duration_minutes": 45},
        "occurred_at": "2026-11-12T10:00:00+05:30",
        "timezone": "Asia/Kolkata",
        "confidence": 0.95,
        "status": "confirmed",
    }

    create_resp = client.post(
        "/api/v1/activities",
        headers=_auth_headers(token),
        json=payload,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()

    assert created["user_id"] == str(user.id)
    assert created["category"] == "development"
    assert created["source"] == "vscode"
    assert created["title"] == "Built REYNA backend authentication"
    assert created["details"] == {"project": "REYNA", "duration_minutes": 45}
    assert created["timezone"] == "Asia/Kolkata"
    assert created["confidence"] == 0.95
    assert created["status"] == "confirmed"

    # 10:00:00+05:30 == 04:30:00Z
    occurred_dt = datetime.fromisoformat(created["occurred_at"])
    recorded_dt = datetime.fromisoformat(created["recorded_at"])
    assert occurred_dt == datetime(2026, 11, 12, 4, 30, 0, tzinfo=timezone.utc)
    assert recorded_dt.tzinfo is not None
    assert recorded_dt != occurred_dt

    # Retrieve single activity by ID
    get_one = client.get(
        f"/api/v1/activities/{created['id']}",
        headers=_auth_headers(token),
    )
    assert get_one.status_code == 200
    assert get_one.json()["id"] == created["id"]


def test_filter_paginate_and_summarize_activities(
    client: TestClient,
    create_user_in_db,
) -> None:
    _, token = create_user_in_db(email="filteruser@example.com")

    records = [
        {
            "category": "development",
            "source": "vscode",
            "title": "Implemented FastAPI router",
            "occurred_at": "2026-11-10T09:00:00Z",
            "timezone": "UTC",
            "status": "confirmed",
        },
        {
            "category": "development",
            "source": "terminal",
            "title": "Ran Alembic migrations",
            "occurred_at": "2026-11-11T12:00:00Z",
            "timezone": "UTC",
            "status": "detected",
        },
        {
            "category": "fitness",
            "source": "garmin",
            "title": "Evening 5km run",
            "occurred_at": "2026-11-12T18:00:00Z",
            "timezone": "UTC",
            "confidence": 0.99,
            "status": "confirmed",
        },
        {
            "category": "reading",
            "source": "kindle",
            "title": "Read Systems Architecture chapter",
            "occurred_at": "2026-11-13T21:00:00Z",
            "timezone": "UTC",
            "status": "manually_entered",
        },
    ]

    for record in records:
        res = client.post("/api/v1/activities", headers=_auth_headers(token), json=record)
        assert res.status_code == 201

    # Pagination
    page1 = client.get(
        "/api/v1/activities?limit=2&offset=0",
        headers=_auth_headers(token),
    )
    assert page1.status_code == 200
    p1_data = page1.json()
    assert p1_data["total"] == 4
    assert len(p1_data["items"]) == 2
    assert p1_data["items"][0]["title"] == "Read Systems Architecture chapter"

    page2 = client.get(
        "/api/v1/activities?limit=2&offset=2",
        headers=_auth_headers(token),
    )
    assert page2.status_code == 200
    assert len(page2.json()["items"]) == 2

    # Category filter
    dev_only = client.get(
        "/api/v1/activities?category=development",
        headers=_auth_headers(token),
    )
    assert dev_only.status_code == 200
    assert dev_only.json()["total"] == 2

    # Source filter
    vscode_only = client.get(
        "/api/v1/activities?source=vscode",
        headers=_auth_headers(token),
    )
    assert vscode_only.status_code == 200
    assert vscode_only.json()["total"] == 1
    assert vscode_only.json()["items"][0]["source"] == "vscode"

    # Date-range filter
    ranged = client.get(
        "/api/v1/activities",
        params={
            "start_date": "2026-11-11T00:00:00Z",
            "end_date": "2026-11-12T23:59:59Z",
        },
        headers=_auth_headers(token),
    )
    assert ranged.status_code == 200
    assert ranged.json()["total"] == 2

    # Summary endpoint
    summary = client.get(
        "/api/v1/activities/summary",
        params={
            "start_date": "2026-11-10T00:00:00Z",
            "end_date": "2026-11-12T23:59:59Z",
        },
        headers=_auth_headers(token),
    )
    assert summary.status_code == 200
    summary_data = summary.json()
    assert summary_data["total_count"] == 3
    assert summary_data["by_category"] == {"development": 2, "fitness": 1}


def test_user_data_isolation_across_all_activity_endpoints(
    client: TestClient,
    create_user_in_db,
) -> None:
    user_a, token_a = create_user_in_db(email="user_a@example.com")
    user_b, token_b = create_user_in_db(email="user_b@example.com")

    create_a = client.post(
        "/api/v1/activities",
        headers=_auth_headers(token_a),
        json={
            "category": "personal",
            "source": "manual",
            "title": "Private journal reflection",
            "occurred_at": "2026-11-12T08:00:00Z",
            "timezone": "UTC",
        },
    )
    assert create_a.status_code == 201
    activity_a_id = create_a.json()["id"]

    create_b = client.post(
        "/api/v1/activities",
        headers=_auth_headers(token_b),
        json={
            "category": "academics",
            "source": "canvas",
            "title": "Submitted algorithms assignment",
            "occurred_at": "2026-11-12T09:00:00Z",
            "timezone": "UTC",
        },
    )
    assert create_b.status_code == 201
    activity_b_id = create_b.json()["id"]

    # User B cannot read User A's activity by changing URL parameter
    cross_read_b = client.get(
        f"/api/v1/activities/{activity_a_id}",
        headers=_auth_headers(token_b),
    )
    assert cross_read_b.status_code == 404

    # User A cannot read User B's activity by changing URL parameter
    cross_read_a = client.get(
        f"/api/v1/activities/{activity_b_id}",
        headers=_auth_headers(token_a),
    )
    assert cross_read_a.status_code == 404

    # List and summary endpoints only return caller's own records
    list_a = client.get("/api/v1/activities", headers=_auth_headers(token_a)).json()
    assert list_a["total"] == 1
    assert list_a["items"][0]["user_id"] == str(user_a.id)

    summary_b = client.get("/api/v1/activities/summary", headers=_auth_headers(token_b)).json()
    assert summary_b["total_count"] == 1
    assert summary_b["by_category"] == {"academics": 1}

    # Non-existent UUID returns 404
    missing = client.get(
        f"/api/v1/activities/{uuid.uuid4()}",
        headers=_auth_headers(token_a),
    )
    assert missing.status_code == 404


def test_invalid_activity_inputs_are_rejected(
    client: TestClient,
    create_user_in_db,
) -> None:
    other_user, _ = create_user_in_db(email="target@example.com")
    _, token = create_user_in_db(email="validator@example.com")

    base_valid = {
        "category": "learning",
        "source": "coursera",
        "title": "Completed lecture 1",
        "occurred_at": "2026-11-12T10:00:00Z",
        "timezone": "UTC",
        "confidence": 0.8,
        "status": "confirmed",
    }

    invalid_cases = [
        # Unknown category
        {**base_valid, "category": "unsupported_category"},
        # Blank source / title
        {**base_valid, "source": "   "},
        {**base_valid, "title": "   "},
        # Naive datetime (missing timezone)
        {**base_valid, "occurred_at": "2026-11-12T10:00:00"},
        # Unknown timezone identifier
        {**base_valid, "timezone": "Mars/Olympus_Mons"},
        # Confidence out of bounds
        {**base_valid, "confidence": 1.5},
        {**base_valid, "confidence": -0.1},
        # Invalid status
        {**base_valid, "status": "unknown_status"},
        # Extra field trying to spoof user_id
        {**base_valid, "user_id": str(other_user.id)},
    ]

    for bad_payload in invalid_cases:
        resp = client.post(
            "/api/v1/activities",
            headers=_auth_headers(token),
            json=bad_payload,
        )
        assert resp.status_code == 422, f"Expected 422 for payload: {bad_payload}"

    # Invalid query date ranges
    bad_range = client.get(
        "/api/v1/activities",
        params={
            "start_date": "2026-11-15T00:00:00Z",
            "end_date": "2026-11-10T00:00:00Z",
        },
        headers=_auth_headers(token),
    )
    assert bad_range.status_code == 422

    naive_query_date = client.get(
        "/api/v1/activities/summary",
        params={"start_date": "2026-11-10T00:00:00"},
        headers=_auth_headers(token),
    )
    assert naive_query_date.status_code == 422

    blank_source = client.get(
        "/api/v1/activities",
        params={"source": "   "},
        headers=_auth_headers(token),
    )
    assert blank_source.status_code == 422

    oversized_details = client.post(
        "/api/v1/activities",
        headers=_auth_headers(token),
        json={**base_valid, "details": {"blob": "x" * (MAX_DETAILS_BYTES + 100)}},
    )
    assert oversized_details.status_code == 422


def test_all_initial_activity_categories_are_supported(
    client: TestClient,
    create_user_in_db,
) -> None:
    _, token = create_user_in_db(email="categories@example.com")
    for category in ActivityCategory:
        resp = client.post(
            "/api/v1/activities",
            headers=_auth_headers(token),
            json={
                "category": category.value,
                "source": "integration-check",
                "title": f"Sample {category.value} event",
                "occurred_at": "2026-11-12T10:00:00Z",
                "timezone": "UTC",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["category"] == category.value

    summary = client.get("/api/v1/activities/summary", headers=_auth_headers(token))
    assert summary.status_code == 200
    assert summary.json()["total_count"] == len(ActivityCategory)
