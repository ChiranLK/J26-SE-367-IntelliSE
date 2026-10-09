"""Environment-based settings for Component 3."""

from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
