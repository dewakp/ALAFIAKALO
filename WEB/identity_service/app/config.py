"""Identity service configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IDENTITY_", extra="ignore")

    # Co-located on ALAFIA's Postgres cluster; isolated in the `identity` schema.
    DATABASE_URL: str = "postgresql+asyncpg://alafia:alafia@db:5432/alafia"
    DB_SCHEMA: str = "identity"

    # Hybrid PQC access-token keys. Loaded from KEYS_FILE (JSON) if set, else from
    # these env vars. If NONE are provided, an ephemeral keypair is generated at
    # boot — allowed in dev (with a warning), but a hard error in production
    # (ephemeral keys break multi-replica SSO and invalidate tokens on restart).
    #   - Ed25519 private key as PKCS8 PEM
    #   - ML-DSA-65 (FIPS 204) secret/public as base64url
    KEYS_FILE: str = ""
    JWT_ED_PRIVATE_KEY: str = ""
    MLDSA_SECRET_KEY: str = ""
    MLDSA_PUBLIC_KEY: str = ""
    # HMAC secret for refresh/reset tokens. These are verified ONLY by the issuer,
    # so a symmetric (already quantum-safe) HMAC keeps them compact (fits cookies).
    HS_SECRET: str = "dev-hs-refresh-secret-change-me"
    ACCESS_TTL_MIN: int = 30
    REFRESH_TTL_DAYS: int = 30
    ISSUER: str = "6igma-identity"
    AUDIENCES: list[str] = ["alafia", "flowsheet"]

    # Shared secret guarding the internal Firebase→IdP password-migration endpoint.
    # An app that has already verified a user's legacy (Firebase) password presents
    # this secret to set the credential in the IdP, completing the migration.
    MIGRATION_SECRET: str = "dev-migration-secret-change-me"

    ENV: str = "development"


settings = Settings()
