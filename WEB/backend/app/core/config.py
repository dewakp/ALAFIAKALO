"""Application configuration via environment variables."""

import warnings

from pydantic_settings import BaseSettings


_INSECURE_SECRET = "change-me-in-production-use-a-long-random-string"


class Settings(BaseSettings):
    APP_NAME: str = "ALAFIA"
    DEBUG: bool = False  # Must be explicitly set to True for development
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://alafia:alafia@localhost:5432/alafia"
    DATABASE_URL_SYNC: str = "postgresql://alafia:alafia@localhost:5432/alafia"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800  # Recycle connections after 30 min

    # Auth / JWT
    SECRET_KEY: str = _INSECURE_SECRET
    ALGORITHM: str = "HS512"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # Shared 6IGMA Identity service (SSO via RS256 JWT verified through JWKS).
    IDENTITY_ENABLED: bool = True
    IDENTITY_BASE_URL: str = "http://identity:8000"
    IDENTITY_ISSUER: str = "6igma-identity"
    IDENTITY_AUDIENCE: str = "alafia"
    # Shared secret for the Firebase→IdP password-migration bridge (must match the
    # identity service's IDENTITY_MIGRATION_SECRET).
    IDENTITY_MIGRATION_SECRET: str = "dev-migration-secret-change-me"

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
    ]

    # Rate Limiting
    RATE_LIMIT_AUTH: str = "5/minute"  # login / register / password-reset
    RATE_LIMIT_DEFAULT: str = "60/minute"

    # Email / SMTP
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@alafia.com"
    SMTP_FROM_NAME: str = "ALAFIA"
    SMTP_TLS: bool = True

    # Error Tracking
    SENTRY_DSN: str = ""  # Set in production for error tracking
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1  # 10% of transactions traced
    SENTRY_ENVIRONMENT: str = "development"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Object Storage (S3-compatible)
    S3_BUCKET: str = ""
    S3_REGION: str = "us-east-1"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_ENDPOINT_URL: str = ""  # Leave blank for AWS; set for MinIO/R2
    S3_CDN_BASE_URL: str = ""  # Optional CloudFront/CDN prefix

    # Blockchain / On-chain anchoring
    CHAIN_NODE_URL: str = "http://chain:8545"  # Private Anvil node (Foundry)

    # AI / LLM — Ollama local inference
    # From Docker: host.docker.internal resolves to the host machine
    # From host (dev): localhost
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_MODEL: str = "gpt-oss:20b"  # 20B model; use llama3.2:latest for faster but weaker responses
    OLLAMA_TIMEOUT: int = 120  # seconds

    # Whisper speech-to-text (Voice Phase 7). Leave WHISPER_BASE_URL empty to use
    # the OpenAI hosted Whisper fallback (requires OPENAI_API_KEY); set it to a
    # self-hosted OpenAI-compatible server (faster-whisper / whisper.cpp) to keep
    # audio on ALAFIA infrastructure.
    WHISPER_BASE_URL: str = ""
    WHISPER_MODEL: str = "whisper-1"

    # OpenAI (cloud fallback for AI nutrient estimation)
    OPENAI_API_KEY: str = ""

    # USDA FoodData Central
    USDA_API_KEY: str = "DEMO_KEY"

    # Firebase (for migration & sync pipeline)
    FIREBASE_SERVICE_ACCOUNT: str = ""  # Path to service account JSON
    FIREBASE_WEB_API_KEY: str = ""  # Firebase Web API key (for password verification)
    FIREBASE_SYNC_ENABLED: bool = False  # Enable real-time Firestore→PG sync
    FIREBASE_SYNC_INTERVAL_SECONDS: int = 300  # Polling interval for sync

    # ── Scheduled practice-facility geocoding (server-side worker) ──────────
    # A background job (APScheduler, in-process with the backend) that upgrades
    # practice-facility coordinates ZIP-fallback → exact via the free US Census
    # batch geocoder. Runs on a fixed cadence; idempotent (only touches rows
    # still lacking precise coords). Disable in test/CI or when running >1 replica.
    PRACTICE_GEOCODE_ENABLED: bool = True
    PRACTICE_GEOCODE_INTERVAL_HOURS: int = 24  # daily
    PRACTICE_GEOCODE_BATCH_LIMIT: int = 5000   # addresses per Census batch call
    PRACTICE_GEOCODE_MAX_BATCHES: int = 6      # cap passes per run (~30k/run)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


# ---------- startup safety checks ----------
def validate_production_settings() -> None:
    """Raise / warn when dangerous defaults are used in production."""
    if not settings.DEBUG and settings.SECRET_KEY == _INSECURE_SECRET:
        raise RuntimeError(
            "SECRET_KEY is still the insecure default. "
            "Set a strong SECRET_KEY environment variable before running in production."
        )
    if settings.SECRET_KEY == _INSECURE_SECRET:
        warnings.warn(
            "SECRET_KEY is the insecure default — acceptable for local dev only.",
            stacklevel=2,
        )
