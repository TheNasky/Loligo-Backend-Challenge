"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Mirrors NestJS ConfigModule / .env pattern."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"

    # App
    app_env: str = "dev"
    app_port: int = 8000
    log_level: str = "INFO"
    message_max_length: int = 4000
    conversation_id_max_length: int = 128
    cors_allow_origins: str = "*"
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 30
    idempotency_ttl_seconds: int = 120
    upstream_timeout_seconds: float = 8.0
    upstream_max_retries: int = 2
    upstream_retry_backoff_seconds: float = 0.35

    # Neon PostgreSQL (optional — in-memory fallback when empty)
    database_url: str = ""

    @property
    def cors_origins(self) -> list[str]:
        raw = self.cors_allow_origins.strip()
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


def validate_runtime_settings(settings: Settings) -> None:
    """Fail fast for unsafe production configuration."""
    if settings.app_env.lower() != "prod":
        return
    if not settings.llm_api_key:
        raise ValueError("LLM_API_KEY is required when APP_ENV=prod")
    if not settings.database_url:
        raise ValueError("DATABASE_URL is required when APP_ENV=prod")
    if settings.cors_allow_origins.strip() == "*":
        raise ValueError(
            "CORS_ALLOW_ORIGINS cannot be '*' when APP_ENV=prod"
        )
    if not settings.cors_origins:
        raise ValueError("CORS_ALLOW_ORIGINS must include at least one origin in production")


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — inject via FastAPI Depends()."""
    return Settings()
