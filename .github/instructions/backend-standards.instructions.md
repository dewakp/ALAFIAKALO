---
applyTo: "WEB/backend/**,WEB/frontend/**"
description: "ALAFIA backend/frontend coding standards — use for all FastAPI, Pydantic, SQLAlchemy, React work."
---

# ALAFIA Backend/Frontend — Domain Instructions

## Backend (FastAPI / Python)

### Non-negotiable rules
- Python 3.11+, async/await throughout — no sync DB calls in async routes
- Pydantic v2 for all request/response schemas in `app/schemas/`
- SQLAlchemy 2.x async ORM — **no raw SQL with user input**
- Type annotations on all public functions and methods
- `logger = logging.getLogger(__name__)` — never `print()` in production paths
- All secrets via environment variables — never hard-code keys

### Route structure
```
POST /resource        → create
GET  /resource        → list
GET  /resource/{id}   → get one
PUT  /resource/{id}   → update
DELETE /resource/{id} → delete
```

### New endpoints checklist
- [ ] Schema in `app/schemas/<domain>.py`
- [ ] Service function in `app/services/<name>.py`
- [ ] Router imported in `app/main.py`
- [ ] Tests in `WEB/backend/tests/test_<domain>.py`
- [ ] No circular imports

### Security (OWASP Top 10)
- All endpoints except `/auth/*` require `get_current_user` dependency
- Validate and sanitize all user-provided strings before use
- File uploads: validate MIME type and size before processing
- Rate-limit sensitive endpoints (auth, AI inference, file upload)

## Frontend (React)

- TypeScript strict mode
- No inline API calls — use the `api/` service layer
- Sensitive data (JWT, user health data) in memory only — not localStorage

## Nutrition API specifics
- `POST /nutrition/estimate-meal` is the primary endpoint for meal logging
- `POST /nutrition/estimate-nutrients` is for single-food lookup
- Always check `aggregate_nutrients` from meal estimate for the saved log values
