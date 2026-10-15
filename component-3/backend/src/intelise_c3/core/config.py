"""Environment-based settings for Component 3."""

from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[3]
COMPONENT_ROOT = BACKEND_ROOT.parent


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

    model_config = SettingsConfigDict(
        env_file=str(COMPONENT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""
    return Settings()
