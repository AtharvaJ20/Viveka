"""Application settings loaded from environment variables.

Never hardcode secrets. Provide a .env file locally (git-ignored);
in production, set env vars directly on the Oracle Cloud instance.

Required env vars:
    DATABASE_URL    — postgresql://user:pass@host:5432/viveka
    SECRET_KEY      — min 32 bytes of random data (used to sign session tokens)

Optional env vars:
    ENVIRONMENT     — 'development' | 'production'  (default: production)
    ALLOWED_EMAILS  — comma-separated allowlist; omit to deny all non-admin
    LLM_COST_CEILING_INR — monthly hard cap in INR (default: 500.0)
    LLM_WARN_THRESHOLD_INR — warning threshold (default: 350.0)
    USD_TO_INR_FALLBACK — fallback rate if FX fetch fails (default: 84.0)
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Database
    DATABASE_URL: str

    # Auth
    SECRET_KEY: str
    SESSION_EXPIRE_DAYS: int = 30

    # Environment
    ENVIRONMENT: str = "production"

    # Allowlist: comma-separated emails that may register/log in.
    # An empty string means the allowlist is enforced but empty — no one can log in.
    # The primary user's email should be the first entry.
    ALLOWED_EMAILS: str = ""

    # LLM cost controls (REQ-034, ADR-005)
    LLM_COST_CEILING_INR: float = 500.0
    LLM_WARN_THRESHOLD_INR: float = 350.0
    USD_TO_INR_FALLBACK: float = 84.0

    # Anthropic API (Phase 4+ active use; env var required before any LLM call)
    ANTHROPIC_API_KEY: str = ""

    @field_validator("DATABASE_URL")
    @classmethod
    def database_url_must_be_postgresql(cls, v: str) -> str:
        if not (v.startswith("postgresql") or v.startswith("postgres")):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @property
    def allowed_emails_set(self) -> frozenset[str]:
        if not self.ALLOWED_EMAILS.strip():
            return frozenset()
        return frozenset(e.strip().lower() for e in self.ALLOWED_EMAILS.split(","))

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def async_database_url(self) -> str:
        """asyncpg URL for SQLAlchemy async engine (FastAPI request handlers)."""
        import re
        return re.sub(
            r"^postgres(?:ql)?(?:\+\w+)?://",
            "postgresql+asyncpg://",
            self.DATABASE_URL,
        )

    @property
    def sync_database_url(self) -> str:
        """psycopg2 URL for sync engine (APScheduler job store)."""
        import re
        return re.sub(
            r"^postgres(?:ql)?(?:\+\w+)?://",
            "postgresql+psycopg2://",
            self.DATABASE_URL,
        )


settings = Settings()  # type: ignore[call-arg]
