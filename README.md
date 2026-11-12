# REYNA

**YOUR LIFE. HER INTELLIGENCE.**

REYNA is a private, personal intelligence and digital life infrastructure platform designed to collect, organize, store, and interpret authorized digital-life data across computers, smartphones, fitness platforms, calendars, academic schedules, reading activity, and development tools.

Long-term, REYNA distinguishes between:
- What you **planned** to do
- What you **actually** did
- What you **completed**
- What you **missed**
- What **patterns** emerge over time

---

## Current Implementation Status — Phase 1: Foundation & Backend

Implemented in Phase 1:
- Modular FastAPI backend with versioned API routes (`/api/v1/...`)
- PostgreSQL integration via SQLAlchemy 2.x and Alembic migrations
- One-time bootstrap token protected initial account registration (`POST /api/v1/auth/setup`, header-only) that permanently disables itself once the first user is created
- Argon2id password hashing (`argon2-cffi`), JWT Bearer authentication (`PyJWT`), and sliding-window brute-force rate limiting on auth endpoints
- Protected user-scoped activity ingestion, retrieval, filtering, pagination, and category summaries
- Health check endpoints (`GET /health`, `GET /api/v1/health`) with database connectivity verification
- Restrictive CORS configuration, HTTP security headers, and production safety guards
- Automated `pytest` + `HTTPX` test suite covering startup, auth, validation, filtering, and user isolation
- Render cloud deployment configuration (`render.yaml`) and [Architecture Documentation](docs/architecture.md)

Intentionally excluded from Phase 1 (planned for future phases):
- AI/LLM pattern analysis
- Desktop/mobile background collectors
- Frontend dashboard UI

---

## Technology Stack

- **Web Framework:** FastAPI
- **ASGI Server:** Uvicorn
- **ORM & Migrations:** SQLAlchemy 2.x + Alembic
- **Database:** Neon Free PostgreSQL (`psycopg[binary]` with automatic `pg8000` pure-Python SSL fallback)
- **Cloud Hosting:** Render Free Web Service (`₹0/month` architecture)
- **Validation & Settings:** Pydantic v2 + `pydantic-settings`
- **Authentication & Hashing:** `PyJWT` + `argon2-cffi` (Argon2id)
- **Testing:** `pytest` + `HTTPX`

---

## Project Folder Structure

```text
REYNA/
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── endpoints/
│   │   │   │   ├── auth.py          # First-account setup, login, current user
│   │   │   │   ├── activities.py    # Record, list, filter, summarize activities
│   │   │   │   └── health.py        # Service and database health checks
│   │   │   └── router.py
│   │   ├── core/
│   │   │   ├── config.py            # Environment settings and validation
│   │   │   ├── security.py          # Argon2 hashing, constant-time token check, JWT
│   │   │   └── dependencies.py      # Bearer token authentication dependency
│   │   ├── db/
│   │   │   ├── base.py              # SQLAlchemy Base and TZDateTime column type
│   │   │   └── session.py           # Engine, SessionLocal, get_db, health query
│   │   ├── models/
│   │   │   ├── user.py              # users table
│   │   │   └── activity.py          # activities table
│   │   ├── schemas/
│   │   │   ├── auth.py              # Auth request/response Pydantic schemas
│   │   │   └── activity.py          # Activity validation, categories, summary schemas
│   │   ├── services/
│   │   │   ├── auth_service.py      # Initial setup and login verification logic
│   │   │   └── activity_service.py  # User-scoped queries and summaries
│   │   └── main.py                  # FastAPI application factory & lifespan
│   ├── migrations/                  # Alembic migration scripts
│   ├── tests/                       # Automated pytest suite
│   ├── alembic.ini
│   └── requirements.txt
├── docs/
│   └── architecture.md              # Detailed architectural guide
├── .env.example                     # Template environment configuration
├── .gitignore
├── render.yaml                      # Render Web Service + PostgreSQL Blueprint
└── README.md
```

---

## Windows Setup Instructions

> **Tip for Windows 11 users:** If Windows Smart App Control blocks `.exe` wrappers inside `.venv\Scripts\` (such as `pytest.exe` or `uvicorn.exe`), run tools via Python directly (`python -m pytest`, `python -m uvicorn`, `python -m alembic`), as shown below.

### 1. Open PowerShell in the project folder

```powershell
cd D:\REYNA\backend
```

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script activation, either run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` or call `.venv\Scripts\python.exe` directly without activating.

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` from the repository root to `.env` (in `D:\REYNA\.env`):

```powershell
Copy-Item ..\.env.example ..\.env
```

Generate strong random values for `SECRET_KEY` and `REYNA_BOOTSTRAP_TOKEN`:

```powershell
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48)); print('REYNA_BOOTSTRAP_TOKEN=' + secrets.token_urlsafe(32))"
```

Open `D:\REYNA\.env` and fill in:
- `SECRET_KEY` (at least 32 random characters)
- `REYNA_BOOTSTRAP_TOKEN` (one-time secret used to create your very first account)
- `DATABASE_URL` (pooled PostgreSQL connection string for FastAPI)
- `DIRECT_URL` (direct PostgreSQL connection string for Alembic migrations)

Never commit `.env` to Git.

### 5. Configure PostgreSQL (Neon Free or Local)

Use either a **Neon Free PostgreSQL** database (recommended for the `₹0/month` cloud architecture) or a local PostgreSQL installation.

- **Option A — Neon Free PostgreSQL (Pooled + Direct separation):**
  - **`DATABASE_URL`**: Paste Neon's **Pooled** connection string (hostname contains `-pooler`, e.g., `ep-...-pooler.us-east-2.aws.neon.tech/...?sslmode=require`). FastAPI and SQLAlchemy use this for application queries.
  - **`DIRECT_URL`**: Paste Neon's **Direct** connection string (hostname **without** `-pooler`, e.g., `ep-....us-east-2.aws.neon.tech/...?sslmode=require`). Alembic migrations and `pg_dump` / `pg_restore` use this direct connection.
- **Option B — Local PostgreSQL:** Create a local user and database:

```sql
CREATE USER reyna_user WITH PASSWORD 'your_strong_password';
CREATE DATABASE reyna_db OWNER reyna_user;
```

Set `DATABASE_URL` and `DIRECT_URL` in `D:\REYNA\.env`:

```env
DATABASE_URL=postgresql+psycopg://reyna_user:your_strong_password@localhost:5432/reyna_db
DIRECT_URL=postgresql+psycopg://reyna_user:your_strong_password@localhost:5432/reyna_db
```

*(Note: Both `postgres://` and `postgresql://` URLs—including Neon's `?sslmode=require&channel_binding=require` strings—are automatically normalized. If `psycopg`'s native extension cannot load on restricted Windows environments, REYNA automatically falls back to pure-Python `pg8000` with SSL enabled.)*

### 6. Run database migrations

From `D:\REYNA\backend`:

```powershell
python -m alembic upgrade head
```

### 7. Start the FastAPI server

From `D:\REYNA\backend`:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Verify health:
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/api/v1/health`

### 8. Access Swagger API documentation

In `development` mode (`ENABLE_DOCS=true`), open:
- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`

In `production`, `ENABLE_DOCS` defaults to `false` to keep internal endpoints private.

### 9. Create your first account & test the API

1. Call `POST /api/v1/auth/setup` with your email, password (8+ chars), and the `Authorization: Bearer <your REYNA_BOOTSTRAP_TOKEN>` header (or `X-Bootstrap-Token` header; tokens in the JSON body are rejected for log safety).
   - Once created, `/api/v1/auth/setup` is permanently disabled and rejects all future calls with `403 Forbidden`.
   - After setup, you may unset/clear `REYNA_BOOTSTRAP_TOKEN` from `.env` or Render.
2. Call `POST /api/v1/auth/login` with `{"email": "...", "password": "..."}` to receive a Bearer JWT `access_token`.
3. Click **Authorize** in Swagger UI and paste your token (or pass `Authorization: Bearer <token>` in requests) to call:
   - `GET /api/v1/auth/me`
   - `POST /api/v1/activities`
   - `GET /api/v1/activities`
   - `GET /api/v1/activities/summary`
   - `GET /api/v1/activities/{activity_id}`

---

## Running Automated Tests

Tests use isolated temporary SQLite databases per test via `pytest` fixtures and run Alembic migrations automatically—they never touch your configured production or development PostgreSQL database.

From `D:\REYNA\backend`:

```powershell
python -m pytest -v
```

---

## Deploying to Render + Neon (`₹0/month` Architecture)

REYNA uses a strict **₹0/month** cloud stack:
- **Backend:** Render Free Web Service (`render.yaml`)
- **Database:** Neon Free PostgreSQL (external managed PostgreSQL over SSL)
- **Source Control:** Public GitHub repository (secrets supplied strictly via Render Environment Variables)

> **Persistence Rule:** Neon is REYNA's sole production database. Render Free Web Services use an **ephemeral filesystem**—never store permanent activity data, SQLite files, or backups on Render's disk.

### Step 1: Create Your Neon Free PostgreSQL Database

1. Sign up for a free Neon account at [neon.com](https://neon.com) (no credit card required).
2. Create a new project (e.g., `reyna-prod`) and choose a region close to your Render region (e.g., US East / EU Central / Singapore).
3. In the Neon Dashboard, click **Connect** and copy **both** connection strings (keeping `?sslmode=require`):
   - **Pooled connection string** (hostname contains `-pooler`) -> goes into **`DATABASE_URL`** (used by FastAPI at runtime).
   - **Direct connection string** (hostname without `-pooler`) -> goes into **`DIRECT_URL`** (used by Alembic migrations, `pg_dump`, and `pg_restore`).
4. **Never commit** either connection string to GitHub or log them.

### Step 2: Deploy on Render (`render.yaml` Blueprint)

1. Push this repository to your **public** GitHub repository after verifying `git status` shows **no** `.env`, `*.db`, backups, or personal files.
2. In the Render Dashboard, choose **New + -> Blueprint** and connect your GitHub repository.
3. Render reads [`render.yaml`](render.yaml) and creates the `reyna-backend` Free Web Service (`plan: free`, `Root Directory: backend`, `ENVIRONMENT=production`, `ENABLE_DOCS=false`).
4. When Render prompts for secret variables (`sync: false`):
   - **`DATABASE_URL`**: Paste your Neon **Pooled** connection string (with `-pooler`).
   - **`DIRECT_URL`**: Paste your Neon **Direct** connection string (without `-pooler`).
   - **`REYNA_BOOTSTRAP_TOKEN`**: Generate a fresh 24+ char random token locally (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) and paste it.
   - *(Render automatically generates `SECRET_KEY` via `generateValue: true`.)*
5. Deploy. Because Render Free Web Services do not support `preDeployCommand`, `render.yaml` executes:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` (`alembic` uses `DIRECT_URL`, while `uvicorn` / FastAPI uses `DATABASE_URL`; in production, Alembic raises a safe configuration error if `DIRECT_URL` is missing rather than falling back to `DATABASE_URL`)
   - **Health Check Path:** `/health`
6. After `GET https://<your-service>.onrender.com/health` returns `{"status": "ok", "database": "connected"}`, register your single owner account once (`POST /api/v1/auth/setup` with `Authorization: Bearer <REYNA_BOOTSTRAP_TOKEN>`), then delete `REYNA_BOOTSTRAP_TOKEN` from Render's Environment Variables.

*(Manual Render setup without Blueprint: create a Free Web Service with `Root Directory` = `backend`, `Build Command` = `pip install -r requirements.txt`, `Start Command` = `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`, `Health Check Path` = `/health`, and configure `ENVIRONMENT=production`, `ENABLE_DOCS=false`, `SECRET_KEY`, `REYNA_BOOTSTRAP_TOKEN`, `DATABASE_URL`, and `DIRECT_URL` in Render's Environment tab.)*

---

## Database Backups & Restore (Windows)

Free-tier databases should not be treated as having guaranteed long-term point-in-time recovery. Take regular local backups to a private folder **outside** `D:\REYNA` (and never commit `.sql` or `.dump` files to your public GitHub repository).

Install PostgreSQL command-line tools on Windows (or `pg_dump` from the PostgreSQL installer). **Always use Neon's Direct (`DIRECT_URL`, without `-pooler`) connection string for `pg_dump` and `pg_restore`**, never the `-pooler` URL, and never paste the URL into committed scripts or logs:

### Export a Backup (`pg_dump`)

```powershell
# Save outside your Git repo, e.g. in your Windows user Backups folder
New-Item -ItemType Directory -Force -Path "$HOME\REYNA_Backups" | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
pg_dump --format=custom --no-owner --no-acl "postgresql://USER:PASSWORD@ep-YOUR-HOST.neon.tech/neondb?sslmode=require" -f "$HOME\REYNA_Backups\reyna_$timestamp.dump"
```

*(For a human-readable SQL file instead, replace `--format=custom` with `--format=plain` and use `.sql` extension.)*

### Restore a Backup (`pg_restore`)

```powershell
# Restore into a clean target database (replace URL with your target Neon direct URL)
pg_restore --clean --if-exists --no-owner --no-acl --dbname="postgresql://USER:PASSWORD@ep-YOUR-HOST.neon.tech/neondb?sslmode=require" "$HOME\REYNA_Backups\reyna_YYYYMMDD_HHMMSS.dump"
```

*(If you exported a `.sql` file instead, restore with `psql "postgresql://..." -f "$HOME\REYNA_Backups\reyna_YYYYMMDD_HHMMSS.sql"`.)*

---

## Free-Tier Limits & Future Scaling Notes

| Platform | Free-Tier Limits to Monitor |
|---|---|
| **Render Free Web Service** | 512 MB RAM; 750 workspace instance hours/month; spins down after **15 min inactivity** (~50–60s cold start on wake); ephemeral filesystem; monthly workspace outbound bandwidth & build minute limits (service suspends or builds pause if exceeded without billing). |
| **Neon Free PostgreSQL** | **1 GB** storage per project; **100 CU-hours/month** compute; auto-suspends compute after **5 min inactivity** (~0.5–2s wake delay); 10 branches; **5 GB/month** public network egress. |

**Future Scaling Note:** Phase 1 uses an in-process sliding-window rate limiter (`SlidingWindowRateLimiter`) so REYNA runs at ₹0/month with zero external Redis service. If REYNA later scales to multiple concurrent backend workers/instances, or adds continuous background ingestion and heavy AI inference pipelines, you will need a shared rate-limit store (e.g., Redis), dedicated background workers, and always-on compute.
