from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Project metadata
    PROJECT_NAME: str = "INTELISE Component 4 - Intelligent Agentic Testing & Feedback Loop Assistant"
    PROJECT_DESCRIPTION: str = (
        "Phase 1 Backend: Independent verification runner, manual code submission, "
        "and structured feedback management for INTELISE."
    )
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS configuration
    ALLOWED_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, (list, str)):
            return v  # type: ignore[return-value]
        raise ValueError(v)

    # Storage Backend: "memory" or "mongodb"
    # Note: "memory" is an ephemeral in-memory repository for local development.
    # Data is lost upon application restart.
    STORAGE_BACKEND: str = "memory"

    # MongoDB Atlas Configuration (optional during Phase 1 development)
    MONGODB_URI: str = ""
    MONGODB_DB_NAME: str = "intelise_component_4"
    MONGODB_CONNECT_TIMEOUT_MS: int = 5000

    # File Upload Constraints
    # Default max upload size: 2MB (2,097,152 bytes)
    MAX_UPLOAD_SIZE_BYTES: int = 2 * 1024 * 1024
    ALLOWED_EXTENSIONS: List[str] = [
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".cs",
        ".go",
        ".rs",
        ".html",
        ".css",
        ".json",
        ".txt",
        ".md",
    ]

    # Logging settings
    LOG_LEVEL: str = "INFO"


settings = Settings()
