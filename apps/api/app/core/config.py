from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

source_path = Path(__file__).resolve()
repository_root = next(
    (parent for parent in source_path.parents if (parent / "PLAN.md").is_file()),
    Path.cwd(),
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(repository_root / ".env", ".env"), extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./cocoon.db"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = Field(default_factory=list)
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    normal_access_token_minutes: int = Field(default=30, ge=15, le=60)
    secret_access_minutes: int = Field(default=5, ge=1, le=15)
    development_biometric_unlock_enabled: bool = False
    refresh_token_days: int = Field(default=30, ge=1, le=90)
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    llm_api_url: str | None = None
    # Self-hosted OpenAI-compatible runtimes commonly do not require a key on the private network.
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: int = Field(default=300, ge=3, le=600)
    assistant_max_concurrent_provider_requests: int = Field(default=2, ge=1, le=8)
    assistant_max_tool_calls: int = Field(default=4, ge=1, le=10)
    assistant_tool_budget_ms: int = Field(default=2000, ge=100, le=10000)
    # The MVP uses one server-side OpenAI-compatible provider, normally Ollama.
    assistant_runtime: str = Field(default="local", pattern=r"^local$")
    # Speech-to-text is deliberately separate from the chat model. It is optional and is
    # only called by the authenticated, short-lived voice transcription endpoint.
    stt_api_url: str | None = None
    stt_api_key: str | None = None
    stt_model: str | None = None
    stt_timeout_seconds: int = Field(default=90, ge=3, le=300)
    expo_push_endpoint: str = "https://exp.host/--/api/v2/push/send"
    worker_interval_seconds: int = Field(default=60, ge=15, le=3600)
    worker_lease_seconds: int = Field(default=600, ge=30, le=3600)
    metrics_token: str | None = Field(default=None, min_length=32)

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_for_plain_postgres_urls(cls, value: object) -> object:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @field_validator("assistant_runtime", mode="before")
    @classmethod
    def default_blank_runtime(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return "local"
        return value

    @field_validator("metrics_token", mode="before")
    @classmethod
    def disable_blank_metrics_token(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
