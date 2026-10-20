"""Environment-based settings for Component 3."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

COMPONENT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Validated service settings loaded from environment variables or .env."""

    service_name: str = "intelise-component-3"
    api_version: str = "v1"
    ollama_base_url: AnyHttpUrl = Field(
        default="http://127.0.0.1:11434",
        description="Base URL of the locally running Ollama service.",
    )
    ollama_model: str = Field(
        default="qwen2.5-coder:3b",
        min_length=1,
        description="Local Ollama coding model name; no cloud fallback is used.",
    )
    ollama_timeout_seconds: float = Field(
        default=120.0,
        gt=0.0,
        le=600.0,
        description="Maximum local Ollama request duration in seconds.",
    )
    ollama_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Deterministic-by-default Ollama sampling temperature.",
    )
    ollama_num_ctx: int = Field(
        default=4096,
        ge=512,
        le=131072,
        description="Requested Ollama context-window size.",
    )
    generated_workspace_root: Path = Field(
        default=COMPONENT_ROOT / "generated-workspaces",
        description="Controlled root for generated application artifacts.",
    )
    traceability_store_path: Path = Field(
        default=COMPONENT_ROOT / "runtime" / "traceability" / "traceability.sqlite3",
        description="Local append-only SQLite traceability snapshot store.",
    )
    rag_enabled: bool = Field(
        default=True,
        description="Enable best-practice retrieval for generation prompts and audit evidence.",
    )
    rag_backend: Literal["filter", "chroma"] = Field(
        default="filter",
        description="Best-practice retrieval backend; filter remains the offline default.",
    )
    rag_persist_dir: Path = Field(
        default=COMPONENT_ROOT / "rag_db",
        description="Local Chroma persistence directory inside Component 3.",
    )
    rag_embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        min_length=1,
        description="Local sentence-transformers model used only by the Chroma backend.",
    )
    teamsoclo_experiment_enabled: bool = Field(
        default=False,
        description="Explicit gate enabling the experimental TeamSocLo Claude workflow.",
    )
    teamsoclo_api_key: str | None = Field(
        default=None,
        description="TeamSocLo API key loaded securely from the environment.",
    )
    teamsoclo_base_url: AnyHttpUrl = Field(
        default="https://gpt.teamsoclo.site",
        description="Base URL of the experimental TeamSocLo gateway.",
    )
    teamsoclo_model: str = Field(
        default="claude-haiku-4-5",
        min_length=1,
        description="Model identifier for experimental Claude inference.",
    )
    teamsoclo_timeout_seconds: float = Field(
        default=120.0,
        gt=0.0,
        le=600.0,
        description="Timeout for experimental TeamSocLo requests in seconds.",
    )

    @field_validator("teamsoclo_model")
    @classmethod
    def normalize_teamsoclo_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("TEAMSOCLO_MODEL must not be blank.")
        if normalized.lower() in {"haiku-4.5", "claude-haiku-4.5"}:
            return "claude-haiku-4-5"
        return normalized

    @field_validator("ollama_base_url")
    @classmethod
    def require_local_ollama_endpoint(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        """Reject remote, authenticated, or path-scoped inference endpoints."""
        local_hosts = {"localhost", "127.0.0.1", "::1", "[::1]"}
        if value.scheme != "http" or value.host not in local_hosts:
            raise ValueError(
                "OLLAMA_BASE_URL must use http and a loopback host "
                "(localhost, 127.0.0.1, or ::1)."
            )
        if value.username is not None or value.password is not None:
            raise ValueError("OLLAMA_BASE_URL must not contain credentials.")
        if value.path not in (None, "", "/") or value.query or value.fragment:
            raise ValueError(
                "OLLAMA_BASE_URL must not contain a path, query, or fragment."
            )
        return value

    @field_validator("ollama_model")
    @classmethod
    def require_local_model_identifier(cls, value: str) -> str:
        """Reject documented Ollama cloud-model tag forms in the local MVP."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("OLLAMA_MODEL must not be blank.")
        lower_name = normalized.lower()
        if lower_name.endswith(":cloud") or lower_name.endswith("-cloud"):
            raise ValueError("OLLAMA_MODEL must identify a local, non-cloud model.")
        return normalized

    @field_validator("generated_workspace_root")
    @classmethod
    def require_component_workspace_root(cls, value: Path) -> Path:
        """Keep API-created workspaces inside Component 3's controlled area."""
        resolved = (
            value.resolve()
            if value.is_absolute()
            else (COMPONENT_ROOT / value).resolve()
        )
        if resolved == COMPONENT_ROOT or not resolved.is_relative_to(COMPONENT_ROOT):
            raise ValueError(
                "GENERATED_WORKSPACE_ROOT must be a child of component-3/."
            )
        return resolved

    @field_validator("traceability_store_path")
    @classmethod
    def require_component_traceability_store(cls, value: Path) -> Path:
        """Keep mutable graph persistence inside Component 3."""
        resolved = (
            value.resolve()
            if value.is_absolute()
            else (COMPONENT_ROOT / value).resolve()
        )
        if resolved == COMPONENT_ROOT or not resolved.is_relative_to(COMPONENT_ROOT):
            raise ValueError(
                "TRACEABILITY_STORE_PATH must be inside component-3/."
            )
        if resolved.suffix not in {".sqlite", ".sqlite3", ".db"}:
            raise ValueError(
                "TRACEABILITY_STORE_PATH must be a .sqlite, .sqlite3, or .db file."
            )
        return resolved

    @field_validator("rag_persist_dir")
    @classmethod
    def require_component_rag_store(cls, value: Path) -> Path:
        """Prevent Chroma from persisting outside the controlled component tree."""
        resolved = value.resolve() if value.is_absolute() else (COMPONENT_ROOT / value).resolve()
        if resolved == COMPONENT_ROOT or not resolved.is_relative_to(COMPONENT_ROOT):
            raise ValueError("RAG_PERSIST_DIR must be a child of component-3/.")
        return resolved

    @field_validator("rag_embedding_model")
    @classmethod
    def normalize_rag_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("RAG_EMBEDDING_MODEL must not be blank.")
        return normalized

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""
    return Settings()
