# REYNA — Phase 1 Backend Architecture

**Tagline:** *YOUR LIFE. HER INTELLIGENCE.*

This document explains how the REYNA Phase 1 backend is organized, why each architectural choice was made, and how the modules work together.

---

## 1. High-Level Design Principles

1. **Privacy and Data Isolation First**: Every personal activity row belongs to a specific `user_id`. All read, list, and summary queries filter by `Activity.user_id == current_user.id` derived strictly from the verified JWT token—never from request bodies or URL parameters.
2. **Separation of Concerns**:
   - **API layer (`app/api/`)**: Handles HTTP routing, request parsing, status codes, and response formatting.
   - **Schema layer (`app/schemas/`)**: Enforces strict input validation (Pydantic v2) and shapes API responses.
   - **Service layer (`app/services/`)**: Encapsulates business rules (bootstrap setup, authentication, activity recording, filtering, summarization).
   - **Model & DB layer (`app/models/`, `app/db/`)**: Defines SQLAlchemy 2.x tables, constraints, indexes, and session lifecycle.
   - **Core layer (`app/core/`)**: Manages environment configuration, Argon2 password hashing, JWT tokens, and authentication dependencies.
3. **Extensibility Without Destructive Migrations**: Activity categories (`smartphone`, `laptop`, `fitness`, `health`, `reading`, `learning`, `development`, `academics`, `calendar`, `personal`) and statuses (`confirmed`, `detected`, `scheduled`, `manually_entered`, `estimated`) are stored as indexed `VARCHAR` columns rather than database-native `ENUM` types. Adding future categories or integrations only requires updating application schemas—not altering database enum types. Flexible integration-specific payloads live in `details` (`JSONB` in PostgreSQL).
4. **Cloud & Local Parity**: Environment variables drive configuration via `pydantic-settings`. Production guards forbid SQLite, reject placeholder secrets, disable public Swagger UI docs by default, and require PostgreSQL.

---

## 2. Directory & Module Breakdown

```text
REYNA/
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── endpoints/
│   │   │   │   ├── auth.py          # /auth/setup, /auth/login, /auth/me
│   │   │   │   ├── activities.py    # /activities CRUD, filtering, summary
│   │   │   │   └── health.py        # /health database connectivity probe
│   │   │   └── router.py            # Aggregates v1 endpoint routers
│   │   ├── core/
│   │   │   ├── config.py            # Environment settings & URL normalization
│   │   │   ├── rate_limit.py        # Sliding-window brute-force protection for auth
│   │   │   ├── security.py          # Argon2 hashing, constant-time bootstrap check, PyJWT
│   │   │   └── dependencies.py      # Bearer JWT extraction & get_current_user
│   │   ├── db/
│   │   │   ├── base.py              # Declarative Base, utcnow(), TZDateTime TypeDecorator
│   │   │   └── session.py           # Engine, SessionLocal, get_db(), health check
│   │   ├── models/
│   │   │   ├── user.py              # User ORM model (users table)
│   │   │   └── activity.py          # Activity ORM model (activities table)
│   │   ├── schemas/
│   │   │   ├── auth.py              # SetupRequest, LoginRequest, UserResponse, TokenResponse
│   │   │   └── activity.py          # ActivityCreate, ActivityResponse, summary & enums
│   │   ├── services/
│   │   │   ├── auth_service.py      # One-time setup logic & user credential verification
│   │   │   └── activity_service.py  # User-scoped creation, filtering, pagination, summary
│   │   └── main.py                  # FastAPI factory, lifespan checks, restrictive CORS
│   ├── migrations/
│   │   ├── env.py                   # Alembic environment wired to Settings & Base.metadata
│   │   ├── script.py.mako           # Migration template
│   │   └── versions/
│   │       └── 0001_initial_schema.py # Initial users & activities schema + indexes
│   ├── tests/                       # Isolated pytest + HTTPX test suite
│   ├── alembic.ini                  # Alembic configuration
│   └── requirements.txt             # Python dependencies
├── docs/
│   └── architecture.md              # This document
├── .env.example                     # Safe placeholder environment variables
├── .gitignore                       # Prevents committing .env, venvs, caches, test DBs
└── README.md                        # Setup, running, testing, and Render deployment guide
```

---

## 3. Key Implementation Decisions (Explained Simply)

### Why Argon2 (`argon2-cffi`) instead of bcrypt?
Argon2id won the Password Hashing Competition and resists GPU/ASIC cracking better than older algorithms. Unlike bcrypt, it has no 72-byte password length truncation limit.

### Why `PyJWT` instead of `python-jose`?
FastAPI's modern security stack recommends `PyJWT` because it is actively maintained and avoids unmaintained transitive dependencies (such as legacy `ecdsa`/`rsa` packages bundled with `python-jose`).

### Why `REYNA_BOOTSTRAP_TOKEN` for `/api/v1/auth/setup` (header-only)?
When you deploy REYNA to a cloud URL (such as Render) for the first time, anyone who guesses the `/setup` URL before you sign up could otherwise claim the first account. Requiring `REYNA_BOOTSTRAP_TOKEN` (24+ chars, placeholders rejected) via request headers (`Authorization: Bearer <token>` or `X-Bootstrap-Token`)—and never in JSON bodies or URLs—minimizes accidental proxy/validation log exposure. Once a single user exists in `users`, `/api/v1/auth/setup` permanently returns `403 Forbidden`. On PostgreSQL, an advisory transaction lock (`pg_advisory_xact_lock`) prevents concurrent first-user race conditions; on single-process local setups, a thread lock serializes setup attempts.

### Why sliding-window rate limiting on `/auth/setup` and `/auth/login`?
Because a cloud deployment exposes `/auth/login` and `/auth/setup` over HTTPS, `app/core/rate_limit.py` applies an in-memory sliding-window rate limiter keyed by client IP and target email (plus a global bucket on `/auth/setup`). This protects single-instance deployments (such as Render Free/Starter) against password and bootstrap-token brute-force attacks while requiring zero external infrastructure in Phase 1. If REYNA later scales horizontally across multiple web workers, this limiter should be backed by a shared Redis store.

### Why separate `occurred_at`, `recorded_at`, and `timezone`?
- `occurred_at` (stored as UTC `TIMESTAMPTZ`) records **when the life event actually happened**—for example, a workout logged offline or synced later.
- `recorded_at` (server-generated UTC `TIMESTAMPTZ`) records **when REYNA received the data**.
- `timezone` preserves the **originating timezone** (e.g., `Asia/Kolkata`) so future intelligence layers understand local time-of-day habits (like "morning" vs "late night") even when you travel across time zones.

### Why `TZDateTime` and `JSON().with_variant(JSONB(), "postgresql")`?
PostgreSQL supports native `JSONB` (fast, indexable binary JSON) and `TIMESTAMPTZ` (timezone-aware timestamps). Local isolated test fixtures using SQLite lack `JSONB` and strip `tzinfo` on datetime reads. Using SQLAlchemy's `with_variant` and `TZDateTime` gives us full native PostgreSQL `JSONB` and `TIMESTAMPTZ` in production while keeping fast, isolated test runs working seamlessly anywhere.

### Why separate `DATABASE_URL` (pooled) and `DIRECT_URL` (direct)?
Neon provides two connection endpoints: a **pooled** PgBouncer hostname (`-pooler`) optimized for application traffic, and a **direct** hostname (without `-pooler`) intended for schema migrations (`alembic upgrade head`) and administration (`pg_dump`/`pg_restore`). REYNA routes runtime FastAPI queries through `DATABASE_URL`, while Alembic reads `DIRECT_URL` (and fails safely in `production` if `DIRECT_URL` is missing rather than silently falling back to a pooled connection).

### Why `postgres://` / `postgresql://` URL normalization & Neon SSL support?
Cloud providers like Render and Neon supply `DATABASE_URL` starting with `postgres://` or `postgresql://` (Neon also appends `?sslmode=require` and optionally `channel_binding=require`). SQLAlchemy 2 + psycopg v3 requires the `postgresql+psycopg://` scheme. `normalize_database_url()` converts provider URLs automatically while preserving query parameters. When running on Windows environments where `psycopg`'s native binary is blocked, `resolve_runtime_database_url()` falls back to pure-Python `pg8000`, translating `sslmode` into a Python `ssl.SSLContext` and stripping unsupported `libpq`-only query flags. Pool settings (`pool_size=5`, `max_overflow=5`, `pool_recycle=300`, `pool_pre_ping=True`) gracefully handle Neon Free's 5-minute idle scale-to-zero behavior.

---

## 4. Request Lifecycle

1. **Startup (`lifespan` in `app/main.py`)**: Validates that `SECRET_KEY` and `DATABASE_URL` are present and not placeholders, initializes the SQLAlchemy connection pool (`pool_pre_ping=True` for PostgreSQL), and configures Swagger docs visibility (`ENABLE_DOCS`).
2. **Authentication (`get_current_user`)**: Reads `Authorization: Bearer <token>`, verifies signature and expiry with `PyJWT`, parses the user UUID from `sub`, and confirms the user exists and `is_active == True`.
3. **Authorization & Isolation**: Every endpoint under `/api/v1/activities` passes `current_user.id` into `activity_service`. If User A requests `GET /api/v1/activities/{user_b_activity_id}`, the query checks `WHERE id = :id AND user_id = :current_user_id`, returning `404 Not Found` so attackers cannot even confirm whether another user's activity UUID exists.
