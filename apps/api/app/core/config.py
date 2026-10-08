from functools import lru_cache
from ipaddress import ip_network
from pathlib import Path

from pydantic import Field, field_validator, model_validator
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
    cors_origins: list[str] = Field(default_factory=list)
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    normal_access_token_minutes: int = Field(default=30, ge=15, le=60)
    secret_access_minutes: int = Field(default=5, ge=1, le=15)
    development_biometric_unlock_enabled: bool = False
    # Exact origin of the web app that invokes navigator.credentials (not the API URL).
    webauthn_origin: str | None = None
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
    # Legacy read-timeout setting; used when LLM_READ_TIMEOUT is absent.
    llm_timeout_seconds: int = Field(default=600, ge=3, le=3600)
    llm_provider: str = Field(default="openai_compatible", pattern=r"^(ollama|openai_compatible)$")
    llm_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str | None = None
    llm_connection_timeout: float = Field(default=20, gt=0)
    llm_read_timeout: float | None = Field(default=None, ge=0)
    llm_pool_timeout: float = Field(default=20, gt=0)
    # Provider-side generation cap; reserve this space when sizing the input context.
    llm_max_output_tokens: int = Field(default=2048, ge=64, le=8192)
    llm_streaming: bool = True
    llm_healthcheck_enabled: bool = True
    assistant_max_concurrent_provider_requests: int = Field(default=2, ge=1, le=8)
    assistant_requests_per_minute: int = Field(default=30, ge=1, le=1000)
    assistant_max_tool_calls: int = Field(default=4, ge=1, le=10)
    assistant_tool_budget_ms: int = Field(default=2000, ge=100, le=10000)
    # Optional local memory search, independent from the conversational provider.
    memory_embeddings_enabled: bool = False
    memory_embedding_base_url: str = "http://localhost:11434"
    memory_embedding_model: str = "qwen3-embedding:0.6b"
    memory_embedding_revision: str = "1"
    memory_embedding_dimensions: int = Field(default=1024, ge=1, le=4096)
    memory_embedding_timeout_seconds: float = Field(default=60, gt=0, le=600)
    memory_query_timeout_seconds: float = Field(default=3, gt=0, le=30)
    memory_vector_enabled: bool = False
    memory_min_similarity: float = Field(default=0.65, ge=0, le=1)
    # Legacy name: this setting currently bounds structured-memory UTF-8 bytes.
    memory_context_tokens: int = Field(default=1200, ge=100, le=8000)
    # UTF-8 prompt estimate, including the system instruction and current message.
    # Configure below the model's real context window to leave room for its answer.
    assistant_prompt_max_bytes: int = Field(default=24000, ge=2000, le=128000)
    memory_worker_interval_seconds: int = Field(default=10, ge=1, le=3600)
    # The MVP uses one server-side OpenAI-compatible provider, normally Ollama.
    assistant_runtime: str = Field(default="local", pattern=r"^local$")
    # Speech-to-text is deliberately separate from the chat model. It is optional and is
    # only called by the authenticated, short-lived voice transcription endpoint.
    stt_api_url: str | None = None
    stt_api_key: str | None = None
    stt_model: str | None = None
    stt_timeout_seconds: int = Field(default=90, ge=3, le=300)
    expo_push_endpoint: str = "https://exp.host/--/api/v2/push/send"
    web_push_public_key: str | None = None
    web_push_private_key: str | None = None
    web_push_subject: str | None = None
    notification_worker_token: str | None = Field(default=None, min_length=32)
    internal_worker_token: str | None = Field(default=None, min_length=32)
    worker_interval_seconds: int = Field(default=60, ge=5, le=3600)
    worker_lease_seconds: int = Field(default=600, ge=30, le=3600)
    metrics_token: str | None = Field(default=None, min_length=32)
    audit_retention_days: int = Field(default=90, ge=7, le=3650)
    # Only peers in these ranges may supply X-Forwarded-For to the audit trail.
    audit_trusted_proxy_cidrs: list[str] = Field(default_factory=list)

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_for_plain_postgres_urls(cls, value: object) -> object:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @field_validator("memory_embedding_base_url")
    @classmethod
    def validate_memory_endpoint(cls, value: str) -> str:
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Le runtime d'embedding requiert une URL HTTP(S) sans identifiants")
        return value.rstrip("/")

    @field_validator("memory_embedding_model", "memory_embedding_revision")
    @classmethod
    def validate_memory_model(cls, value: str) -> str:
        if not value.strip() or len(value) > 160:
            raise ValueError("Le modèle et sa révision doivent être non vides et bornés")
        return value.strip()

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

    @field_validator("notification_worker_token", "internal_worker_token", mode="before")
    @classmethod
    def disable_blank_notification_worker_token(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("expo_push_endpoint", mode="before")
    @classmethod
    def default_blank_expo_endpoint(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return "https://exp.host/--/api/v2/push/send"
        return value

    @field_validator("audit_trusted_proxy_cidrs")
    @classmethod
    def validate_audit_trusted_proxies(cls, value: list[str]) -> list[str]:
        for cidr in value:
            network = ip_network(cidr, strict=False)
            if network.prefixlen == 0:
                raise ValueError("Un proxy de confiance ne peut pas couvrir toutes les adresses IP")
        return value

    @model_validator(mode="after")
    def validate_llm_configuration(self) -> "Settings":
        from urllib.parse import urlparse

        url = (
            self.ollama_base_url
            if self.llm_provider == "ollama"
            else self.llm_base_url or self.llm_api_url
        )
        model = self.ollama_model if self.llm_provider == "ollama" else self.llm_model
        if self.llm_provider == "ollama" and not model:
            raise ValueError("OLLAMA_MODEL est requis avec LLM_PROVIDER=ollama")
        if self.llm_provider == "openai_compatible" and bool(url) != bool(model):
            raise ValueError(
                "LLM_BASE_URL (ou LLM_API_URL) et LLM_MODEL doivent être définis ensemble"
            )
        if url:
            parsed = urlparse(url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError(
                    "L'URL du fournisseur LLM doit être une URL HTTP(S) sans identifiants"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
