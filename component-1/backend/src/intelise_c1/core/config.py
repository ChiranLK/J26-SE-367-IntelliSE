"""Environment settings; database credentials are kept out of repr output."""

from urllib.parse import urlsplit
from pathlib import Path
import tempfile
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="C1_", env_file=".env", env_file_encoding="utf-8", extra="ignore",
        populate_by_name=True,
    )

    backend_host: str = Field(default="127.0.0.1", min_length=1)
    backend_port: int = Field(default=8001, ge=1, le=65535)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    mongodb_uri: SecretStr | None = Field(default=None, validation_alias="MONGODB_URI")
    mongodb_database: str = Field(
        default="intellise_component_1", validation_alias="MONGODB_DATABASE",
        pattern=r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,62}$",
    )
    mongodb_timeout_ms: int = Field(default=2000, ge=100, le=10000)

    llm_provider: Literal["anthropic", "ollama"] = "anthropic"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = Field(default="llama3.2:1b", min_length=1, max_length=200)
    ollama_context_length: int = Field(default=2048, ge=512, le=131072)

    ollama_max_tokens: int = Field(default=256, ge=32, le=16384)

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"} or any(c.isspace() for c in value)):
            raise ValueError("Ollama URL must be an HTTP(S) origin without credentials")
        _ = parsed.port
        return value.rstrip("/")

    @field_validator("ollama_model")
    @classmethod
    def validate_ollama_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Ollama model must not be blank")
        return value

    anthropic_api_key: SecretStr | None = None
    llm_model: str = Field(default="", max_length=200)
    llm_timeout_seconds: float = Field(default=60, ge=1, le=180)
    llm_max_tokens: int = Field(default=8192, ge=256, le=16384)
    llm_response_max_bytes: int = Field(default=262144, ge=1024, le=1048576)
    extraction_max_characters: int = Field(default=30000, ge=1, le=100000)
    classifier_model_dir: Path | None = None
    transcription_provider: Literal["whisper", "azure"] = "whisper"
    azure_speech_key: SecretStr | None = None
    azure_speech_endpoint: str = "https://southeastasia.api.cognitive.microsoft.com"
    azure_speech_api_version: Literal["2025-10-15"] = "2025-10-15"
    azure_speech_locale: Literal["en-US", "en-GB", "en-IN", "en-AU"] = "en-US"
    audio_ffmpeg_path: Path | None = None

    @field_validator("azure_speech_endpoint")
    @classmethod
    def azure_endpoint(cls, value):
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or not host.endswith((".api.cognitive.microsoft.com", ".cognitiveservices.azure.com"))
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or any(character.isspace() for character in value)):
            raise ValueError("Use the HTTPS Azure Speech resource endpoint without credentials or a path")
        return value.rstrip("/")

    whisper_python: Path | None = None
    whisper_model: str = Field(default="tiny.en", pattern=r"^(tiny|base|small|medium)(\.en)?$|^large(-v[123])?$|^turbo$")
    whisper_model_dir: Path = Path("models/whisper")
    audio_temp_dir: Path = Path(tempfile.gettempdir()) / "intellise-c1-audio"
    audio_max_bytes: int = Field(default=10000000, ge=1024, le=100000000)
    audio_max_seconds: float = Field(default=120, ge=1, le=600)
    audio_queue_size: int = Field(default=2, ge=0, le=10)
    audio_decode_timeout_seconds: float = Field(default=20, ge=1, le=120)
    audio_processing_timeout_seconds: float = Field(default=300, ge=1, le=1800)
    audio_silence_rms: float = Field(default=0.0001, ge=0, le=0.01)

    @field_validator("whisper_python", "audio_ffmpeg_path", mode="before")
    @classmethod
    def optional_whisper_python(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("classifier_model_dir", mode="before")
    @classmethod
    def optional_model_directory(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
                or any(character.isspace() for character in origin)
            ):
                raise ValueError("CORS origins must be explicit HTTP(S) origins without paths")
            # Accessing port validates malformed or out-of-range port values.
            _ = parsed.port
        return origins
