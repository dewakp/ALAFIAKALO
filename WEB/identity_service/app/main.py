"""6IGMA Shared Identity Service — PostgreSQL-native IdP for ALAFIA + FlowSheet.

One identity store, zero duplication (docs/IDENTITY_ARCHITECTURE.md). Issues RS256
JWTs both apps verify via JWKS for cross-app SSO.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import init_db
from app.security import jwks
from app.routers import auth, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()  # CREATE SCHEMA identity + tables (skeleton; Alembic later)
    yield


app = FastAPI(title="6IGMA Identity Service", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(users.router)


@app.get("/.well-known/jwks.json", tags=["jwks"])
async def jwks_endpoint():
    """Public keys so ALAFIA + FlowSheet verify identity JWTs offline."""
    return jwks()


@app.get("/identity/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "6igma-identity", "env": settings.ENV,
            "issuer": settings.ISSUER, "audiences": settings.AUDIENCES}
