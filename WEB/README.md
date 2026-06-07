# ALAFIA — Holistic Health Platform (WEB)

A fullstack web application for holistic personal health management: **Nutrition, Fitness, Labs (EHR-compliant), Medications, Mood/Mental Health, Lifestyle** — powered by a custom AI assistant.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic |
| **Frontend** | React 19, Vite, React Router 7, Recharts |
| **Database** | PostgreSQL 16 |
| **Auth** | JWT (python-jose + passlib/bcrypt) |
| **AI** | Pluggable LLM engine (stub ready) |
| **DevOps** | Docker Compose |

## Project Structure

```
WEB/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   └── app/
│       ├── main.py              # FastAPI entry point
│       ├── core/
│       │   ├── config.py        # Settings (env vars)
│       │   ├── database.py      # Async SQLAlchemy engine
│       │   └── security.py      # JWT + password hashing
│       ├── models/              # SQLAlchemy ORM models
│       │   ├── user.py
│       │   ├── nutrition.py
│       │   ├── fitness.py
│       │   ├── labs.py
│       │   ├── medications.py
│       │   ├── mood.py
│       │   └── lifestyle.py
│       ├── schemas/             # Pydantic request/response schemas
│       │   ├── user.py
│       │   ├── nutrition.py
│       │   ├── fitness.py
│       │   ├── labs.py
│       │   ├── medications.py
│       │   ├── mood.py
│       │   ├── lifestyle.py
│       │   └── ai.py
│       └── api/                 # Route handlers
│           ├── __init__.py      # Router aggregation
│           ├── auth.py
│           ├── users.py
│           ├── nutrition.py
│           ├── fitness.py
│           ├── labs.py
│           ├── medications.py
│           ├── mood.py
│           ├── lifestyle.py
│           └── ai.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── index.css
        ├── services/api.js
        ├── context/AuthContext.jsx
        ├── components/Layout.jsx
        └── pages/
            ├── Login.jsx
            ├── Register.jsx
            ├── Dashboard.jsx
            ├── Nutrition.jsx
            ├── Fitness.jsx
            ├── Labs.jsx
            ├── Medications.jsx
            ├── Mood.jsx
            ├── Lifestyle.jsx
            └── AIChat.jsx
```

## Quick Start

### Option 1: Docker Compose (recommended)

```bash
cd WEB
docker compose up --build
```

- **Frontend**: http://localhost:5173
- **Backend API docs**: http://localhost:8000/api/docs
- **PostgreSQL**: localhost:5432

### Option 2: Local Development

#### 1. Start PostgreSQL

```bash
# Using Docker for just the database:
docker run -d --name alafia-db \
  -e POSTGRES_USER=alafia \
  -e POSTGRES_PASSWORD=alafia \
  -e POSTGRES_DB=alafia \
  -p 5432:5432 postgres:16-alpine
```

#### 2. Backend

```bash
cd WEB/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic revision --autogenerate -m "initial"
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload --port 8000
```

#### 3. Frontend

```bash
cd WEB/frontend
npm install
npm run dev
```

## API Endpoints

| Module | Endpoints |
|--------|-----------|
| **Auth** | `POST /api/v1/auth/register`, `POST /api/v1/auth/login` |
| **Users** | `GET/PATCH /api/v1/users/me` |
| **Nutrition** | `GET/POST /api/v1/nutrition/`, `GET/PATCH/DELETE /api/v1/nutrition/:id` |
| **Fitness** | `GET/POST /api/v1/fitness/`, `GET/PATCH/DELETE /api/v1/fitness/:id` |
| **Labs** | `GET/POST /api/v1/labs/`, `GET/PATCH/DELETE /api/v1/labs/:id` |
| **Medications** | `GET/POST /api/v1/medications/`, `GET/PATCH/DELETE /api/v1/medications/:id` |
| **Mood** | `GET/POST /api/v1/mood/`, `GET/PATCH/DELETE /api/v1/mood/:id` |
| **Lifestyle** | `GET/POST /api/v1/lifestyle/`, `GET/PATCH/DELETE /api/v1/lifestyle/:id` |
| **AI** | `POST /api/v1/ai/chat` |
| **Health** | `GET /api/health` |

Full interactive API docs available at **http://localhost:8000/api/docs** (Swagger UI).

## Environment Variables

See `backend/.env` for all configurable values:
- `DATABASE_URL` — PostgreSQL connection string
- `SECRET_KEY` — JWT signing key (change in production!)
- `LLM_API_KEY` — API key for your LLM engine
- `CORS_ORIGINS` — Allowed frontend origins

## EHR Compliance

The Labs module supports:
- **LOINC codes** for standardized test identification
- **FHIR-aligned** data model (Observation resource pattern)
- Reference ranges with abnormal flagging
- Status tracking (registered → partial → final → amended)

The Medications module supports:
- **RxNorm codes** for drug identification
- Full prescription metadata (dosage, frequency, route, prescriber)

## Next Steps

- [ ] Integrate custom LLM engine in `app/api/ai.py`
- [ ] Add data visualization charts (Recharts already included)
- [ ] FHIR R4 export/import for lab results
- [ ] Notification system for medication reminders
- [ ] Mobile API compatibility (shared backend)
