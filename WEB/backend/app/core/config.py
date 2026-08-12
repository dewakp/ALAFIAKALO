"""Application configuration via environment variables."""

import warnings

from pydantic_settings import BaseSettings


_INSECURE_SECRET = "change-me-in-production-use-a-long-random-string"


class Settings(BaseSettings):
    APP_NAME: str = "ALAFIA"
    # Deployed git commit — stamped at deploy time (deploy.sh) and surfaced by
    # /api/health so prod can be verified byte-for-byte against a dev commit.
    GIT_SHA: str = "dev"
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

    # ── Email ────────────────────────────────────────────────────────────
    # Resend is preferred over raw SMTP: it is an HTTPS call, so it is immune to
    # the outbound-port and TLS-negotiation problems SMTP hits on serverless
    # hosts, and it returns a message id and a real error body instead of a
    # generic socket failure. SMTP stays as the fallback for self-hosting.
    RESEND_API_KEY: str = ""
    RESEND_API_BASE: str = "https://api.resend.com"

    # Email / SMTP (fallback when RESEND_API_KEY is unset)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    # alafia.app is the ONLY domain we own. Its DNS is in Cloud DNS (zone
    # `alafia-app`, project alafia-prod-6igma) and it is the domain verified in
    # Resend, so it is the only domain we can send from. Do not reintroduce
    # alafia.com anywhere — it belongs to someone else.
    SMTP_FROM_EMAIL: str = "noreply@alafia.app"
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

    # ── EHR / MyChart (SMART on FHIR patient access) ────────────────────────
    # Client ID from an Epic app registration (fhir.epic.com). One non-prod +
    # one prod ID cover every Epic-hosted portal (Kaiser, Trinity Health, …).
    EPIC_CLIENT_ID: str = ""
    # Where the portal redirects after the patient signs in. Must exactly match
    # the redirect URI on the Epic app registration.
    EHR_REDIRECT_URI: str = "http://localhost:8080/ehr/callback"
    # Expose the registration-free SMART Health IT sandbox as a connectable
    # "organization" for local testing/demo (works without EPIC_CLIENT_ID).
    EHR_ENABLE_SANDBOX: bool = True

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

    # ── Subscription / Billing ──────────────────────────────────────────────
    # A single paid tier ("ALAFIA Membership"). Prices are USD/month and differ by the
    # rail because the mobile stores take a cut. The BACKEND is the single source
    # of truth for entitlement: each rail reports a verified purchase and the
    # backend records the active period. If a provider's keys are blank the
    # matching rail runs in dev "test-mode" — it returns a fake but internally
    # consistent purchase so the UI + entitlement flow can be exercised without
    # live credentials (never enabled when DEBUG is False).
    SUBSCRIPTION_ENABLED: bool = True
    SUBSCRIPTION_PRODUCT_NAME: str = "ALAFIA Membership"
    SUBSCRIPTION_PRICE_WEB_USD: float = 12.0        # Stripe / PayPal (monthly)
    SUBSCRIPTION_PRICE_ANDROID_USD: float = 14.0    # Google Play Billing (monthly)
    SUBSCRIPTION_PRICE_IOS_USD: float = 14.0        # Apple StoreKit (monthly)
    # Annual web plan (Stripe / PayPal). ~$10.75/mo vs $12/mo monthly.
    SUBSCRIPTION_PRICE_WEB_ANNUAL_USD: float = 129.0
    SUBSCRIPTION_TRIAL_DAYS: int = 0
    # Grace window after a period ends before entitlement is revoked (covers
    # webhook lag / renewal retries).
    SUBSCRIPTION_GRACE_DAYS: int = 3
    # App-wide paywall: when True, EVERY authenticated data request requires an
    # active subscription (402 otherwise). Auth / subscription / users endpoints stay
    # open so a user can still sign in, see their status, and pay. Off by default
    # (dev / self-host); enable in production.
    SUBSCRIPTION_REQUIRED: bool = False
    # Emails that bypass the paywall entirely (owner / staff), comma-separated in env.
    # dew@6igma.com is included because the admin console lives under /api/v1 and
    # would otherwise be 402'd by the paywall in production before reaching it.
    # ios_reviewr@alafia.app is Apple's App Review demo account. It must reach the
    # app's actual functionality or review fails: with the hard paywall on, every
    # gated endpoint 402s an unsubscribed user, so a reviewer signing in with the
    # demo credentials would see nothing but "membership required" and reject the
    # build. Exempting it is deliberate and preferable to writing a fake
    # subscription row, which would make a non-paying account indistinguishable
    # from a real subscriber in billing and admin reporting.
    # NOTE: set here rather than in deploy.sh because this field is a list[str] and
    # pydantic-settings parses complex types from env as JSON — a comma-separated
    # value would fail at startup.
    SUBSCRIPTION_EXEMPT_EMAILS: list[str] = [
        "developer@hntsolutions.com",
        "dew@6igma.com",
        "ios_reviewr@alafia.app",
    ]

    # ── Signup ───────────────────────────────────────────────────────────
    # Direct registration created a `users` row on request, which is how 55 of
    # 77 accounts in this database became `*@example.com` automation leftovers.
    # With this on, /auth/register is closed and the only way to an account is
    # /auth/signup/* — email verified AND subscription paid, in that order.
    # Set false only to re-open the legacy path deliberately.
    TWO_STEP_SIGNUP_REQUIRED: bool = True

    # ── Admin console ────────────────────────────────────────────────────
    # Who may reach /api/v1/admin/*. Deliberately an explicit allowlist rather
    # than the `is_superuser` flag alone: that flag is currently set on a leftover
    # test account (crossapp_…@example.com), and one stray UPDATE should not be
    # able to hand out console access. BOTH must hold — email on this list AND
    # the account active.
    ADMIN_EMAILS: list[str] = ["dew@6igma.com"]
    # Public base URL of the web app; used to build Stripe/PayPal return URLs.
    PUBLIC_WEB_URL: str = "http://localhost:8080"

    # Stripe (web card rail). Blank STRIPE_SECRET_KEY ⇒ dev test-mode checkout.
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PRICE_ID: str = ""            # price_… recurring $12/mo price
    STRIPE_PRICE_ID_ANNUAL: str = ""     # price_… recurring $129/yr price
    STRIPE_WEBHOOK_SECRET: str = ""      # whsec_… for signature verification
    STRIPE_API_BASE: str = "https://api.stripe.com"

    # PayPal (web alternative rail).
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_PLAN_ID: str = ""             # P-… billing plan for the $12/mo sub
    PAYPAL_PLAN_ID_ANNUAL: str = ""      # P-… billing plan for the $129/yr sub
    PAYPAL_WEBHOOK_ID: str = ""          # for webhook signature verification
    PAYPAL_API_BASE: str = "https://api-m.sandbox.paypal.com"  # live: api-m.paypal.com

    # Google Play Billing (Android). Server-side purchase verification via a
    # service account with the Android Publisher scope.
    GOOGLE_PLAY_PACKAGE_NAME: str = "com.alafia.android"
    GOOGLE_PLAY_PRODUCT_ID: str = "alafia_plus_monthly"
    GOOGLE_PLAY_SERVICE_ACCOUNT: str = ""   # path to service-account JSON

    # Apple StoreKit (iOS). Server-side transaction verification.
    APPLE_BUNDLE_ID: str = "com.alafia.app"   # matches the iOS Xcode bundle + alafia.app domain
    APPLE_PRODUCT_ID: str = "alafia_plus_monthly"
    APPLE_PRODUCT_ID_ANNUAL: str = "alafia_plus_annual"
    APPLE_SHARED_SECRET: str = ""           # app-specific shared secret (verifyReceipt)
    APPLE_ENVIRONMENT: str = "sandbox"      # sandbox | production

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
