"""
app/core/config.py — Settings: the single point of contact with os.environ for app/.

Why pydantic-settings (BaseSettings) instead of a dataclass like every other
Sprint's *Config.from_env():
    Every prior config class (SpeechProcessingConfig, ExtractionConfig,
    GenerationConfig, DatabaseConfig) is a plain dataclass with a hand-written
    from_env() classmethod — appropriate for a handful of internal tunables
    read by one module. app/core/config.py is different: it backs public
    HTTP behavior (CORS, JWT expiry, environment-gated debug mode) where
    Pydantic's validation, type coercion, and .env file support pay for
    themselves. BaseSettings is also the FastAPI-ecosystem convention, so a
    future engineer reading this file recognizes the pattern immediately.

Why Settings does NOT redeclare DATABASE_URL / GROQ_API_KEY / etc.:
    Those env vars already have an authoritative owner: DatabaseConfig,
    ExtractionConfig, GenerationConfig, SpeechProcessingConfig each read
    their own slice of os.environ via from_env(). Redeclaring GROQ_API_KEY
    here would create two independent readers of the same env var — a
    classic source of drift if one is updated and the other isn't. Instead,
    Settings exposes factory *methods* (database_config(), extraction_config(),
    ...) that delegate to the existing from_env() classmethods. app/ code
    that needs a DailyLogRepository or a GroqEngine goes through these
    methods, never constructs a *Config directly.

Why one Settings class with an `environment` discriminator, not three
separate Dev/Test/ProdSettings subclasses:
    Every existing config class in this repo (Sprints 3-6) is a single flat
    class read from one .env file — there is no established pattern of
    per-environment subclasses anywhere in the codebase. A single class with
    one Literal field (`environment`) that gates a handful of derived
    properties (`.debug`, `.cors_origins`) achieves the same outcome with
    less code to keep in sync, and it matches how every other Sprint already
    does this. If this project later needs meaningfully different behavior
    per environment (not just toggles), splitting into subclasses at that
    point is a small, localized change — nothing downstream depends on
    Settings being a single class.

Environment variables read by THIS file (app/-specific):
    ENVIRONMENT              development | testing | production (default: development)
    JWT_SECRET_KEY            HMAC signing secret (default: dev-only fallback — see docstring)
    JWT_ALGORITHM              default: HS256
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES  default: 60
    REFRESH_TOKEN_EXPIRE_DAYS  default: 30 (Sprint 8)
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES  default: 30 (Sprint 8)
    CORS_ALLOW_ORIGINS         comma-separated list (default: "*" in development only)
    APP_TITLE / APP_DESCRIPTION / APP_VERSION / APP_CONTACT_EMAIL  OpenAPI metadata
    DEV_SEED_ADMIN_EMAIL / DEV_SEED_ADMIN_PASSWORD  dev-only demo login (see app/core/security.py)

Everything else (DATABASE_URL, GROQ_API_KEY, SPEECH_*, EXTRACTION_*,
GENERATION_*) continues to be read exclusively by its Sprint 1-6 owner.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from database.config import DatabaseConfig
from extraction.config import ExtractionConfig
from generation.config import GenerationConfig
from speech.config import SpeechProcessingConfig


class Settings(BaseSettings):
    """Application settings for the app/ FastAPI backend.

    Construct via get_settings() (cached) in application code — never
    instantiate Settings() directly outside of tests, so the whole process
    shares one parsed configuration.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env has many Sprint 1-6 vars this class does not declare
        case_sensitive=False,
    )

    # ── Environment ───────────────────────────────────────────────────────────
    environment: Literal["development", "testing", "production"] = Field(
        default="development",
        description="Gates debug mode and default CORS permissiveness.",
    )

    # ── App / OpenAPI metadata ───────────────────────────────────────────────
    app_title: str = "Construction Site AI API"
    app_description: str = (
        "Converts foreman voice recordings into structured daily logs and "
        "AI-generated business documents (daily reports, customer updates, "
        "safety talks, material reminders)."
    )
    app_version: str = "0.7.0"
    app_contact_name: str = "Construction Site AI"
    app_contact_email: str = "support@example.com"

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret_key: str = Field(
        default="dev-insecure-secret-change-me",
        description=(
            "HMAC signing secret for JWT access tokens. The default is "
            "INSECURE and only acceptable in `development`/`testing` — "
            "production startup fails fast if this default is still in use "
            "(see create_app.py lifespan check)."
        ),
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # ── Refresh tokens / sessions (Sprint 8) ─────────────────────────────────
    refresh_token_expire_days: int = Field(
        default=30,
        description=(
            "How long an unused refresh token remains valid. Each successful "
            "POST /auth/refresh issues a new one with a fresh expiry "
            "('rotation'), so an active user is never logged out — this "
            "value only matters for a genuinely abandoned session."
        ),
    )
    password_reset_token_expire_minutes: int = Field(
        default=30,
        description=(
            "How long a password-reset token is valid. Short-lived by "
            "design — see docs/AUTHENTICATION_ARCHITECTURE.md 'Forgot Password'."
        ),
    )

    # ── Account lockout (Sprint 8, Subsystem 5) ──────────────────────────────
    lockout_max_failed_attempts: int = Field(
        default=5,
        description="Consecutive failed logins before an account is locked.",
    )
    lockout_duration_minutes: int = Field(
        default=15,
        description="How long an account stays locked after hitting "
        "lockout_max_failed_attempts. Cleared early by admin unlock or "
        "password reset.",
    )

    # ── Rate limiting (Sprint 8, Subsystem 5) ────────────────────────────────
    # In-memory for Sprint 8 (see app/core/rate_limit.py) — these limits
    # apply per-process; see that module's docstring for the documented
    # multi-worker/restart limitation and docs/DECISIONS.md for the
    # planned Redis migration.
    rate_limit_login_attempts: int = Field(
        default=10,
        description="Max POST /auth/login attempts per email within "
        "rate_limit_login_window_seconds — a coarser, IP/email-agnostic "
        "backstop layered on top of the per-account lockout above.",
    )
    rate_limit_login_window_seconds: int = Field(default=300)
    rate_limit_forgot_password_attempts: int = Field(
        default=3,
        description="Max POST /auth/forgot-password requests per email "
        "within rate_limit_forgot_password_window_seconds — prevents "
        "using the reset-token-generation endpoint as a spam/enumeration "
        "vector even though it never confirms whether an email exists.",
    )
    rate_limit_forgot_password_window_seconds: int = Field(default=3600)

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_allow_origins_raw: str = Field(default="*", alias="CORS_ALLOW_ORIGINS")

    # ── Dev-only seeded login (see app/core/security.py, database/seed/) ─────
    dev_seed_admin_email: str = "admin@example.com"
    dev_seed_admin_password: str = "Admin@123"

    # ── Derived properties ────────────────────────────────────────────────────

    @property
    def debug(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_allow_origins(self) -> List[str]:
        """Parsed CORS origin list.

        "*" (the default) is fine for local development but is rejected at
        startup in production — see create_app.py.
        """
        raw = self.cors_allow_origins_raw.strip()
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    # ── Sprint 1-6 config delegation (composition, not duplication) ─────────

    @staticmethod
    def database_config() -> DatabaseConfig:
        """Return the Sprint 6 DatabaseConfig, read from DATABASE_URL etc."""
        return DatabaseConfig.from_env()

    @staticmethod
    def extraction_config() -> ExtractionConfig:
        """Return the Sprint 4 ExtractionConfig, read from EXTRACTION_*/GROQ_API_KEY."""
        return ExtractionConfig.from_env()

    @staticmethod
    def generation_config() -> GenerationConfig:
        """Return the Sprint 5 GenerationConfig, read from GENERATION_*/GROQ_API_KEY."""
        return GenerationConfig.from_env()

    @staticmethod
    def speech_config() -> SpeechProcessingConfig:
        """Return the Sprint 3 SpeechProcessingConfig, read from SPEECH_*."""
        return SpeechProcessingConfig.from_env()


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance.

    Use as a FastAPI dependency: `settings: Settings = Depends(get_settings)`.
    lru_cache means Settings is parsed from the environment exactly once per
    process — subsequent calls (including every request) return the same
    instance. Tests that need a different configuration call
    get_settings.cache_clear() after monkeypatching os.environ, or construct
    Settings(...) directly with explicit overrides.
    """
    return Settings()
