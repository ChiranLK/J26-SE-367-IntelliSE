import secrets
from typing import List, Union
from pydantic import Field, field_validator
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
    # Default max upload size: 5MB (5,242,880 bytes)
    MAX_UPLOAD_SIZE_BYTES: int = 5 * 1024 * 1024
    MAX_PROJECT_ZIP_FILES: int = 100
    MAX_PROJECT_UNCOMPRESSED_BYTES: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: List[str] = [
        ".py",
        ".zip",
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

    # Docker Test Runner Sandbox Configuration (Phase 2B)
    DOCKER_RUNNER_IMAGE: str = "intelise-python-runner:3.12-v2"
    DOCKER_TIMEOUT_SECONDS: int = 15
    DOCKER_MEMORY_LIMIT: str = "256m"
    DOCKER_CPU_LIMIT: str = "1.0"
    DOCKER_PIDS_LIMIT: int = 64
    DOCKER_TMPFS_SIZE: str = "64m"

    # Component 3 Outbound Feedback Integration (Phase 4 Milestone 1)
    # Disabled by default until Component 3 implements a verified feedback receiver endpoint
    COMPONENT_3_ENABLED: bool = False
    COMPONENT_3_BASE_URL: str = "http://127.0.0.1:8000"
    COMPONENT_3_FEEDBACK_ENDPOINT: str = "/api/v1/correction-feedback"
    COMPONENT_3_TIMEOUT_SECONDS: float = 10.0
    COMPONENT_3_CONNECT_TIMEOUT_SECONDS: float = 3.0
    COMPONENT_3_MAX_RETRIES: int = 2
    COMPONENT_3_API_KEY: str = ""

    @field_validator("COMPONENT_3_BASE_URL", mode="after")
    @classmethod
    def validate_component_3_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("COMPONENT_3_BASE_URL must begin with http:// or https://")
        return v.rstrip("/")

    # Ollama Local LLM Configuration (Research Proposal Gap Closure)
    OLLAMA_ENABLED: bool = True
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:3b"
    # OLLAMA_TIMEOUT_SECONDS is retained for compatibility with existing callers.
    OLLAMA_TIMEOUT_SECONDS: float = 60.0
    OLLAMA_CONNECT_TIMEOUT_SECONDS: float = 5.0
    OLLAMA_READ_TIMEOUT_SECONDS: float = 120.0
    OLLAMA_MAX_OUTPUT_TOKENS: int = 800
    OLLAMA_KEEP_ALIVE: str = "10m"

    # Multi-Agent Test Runner Configuration
    PERFORMANCE_TEST_ITERATIONS: int = 10
    PERFORMANCE_LATENCY_THRESHOLD_MS: float = 200.0

    # Production Delivery Authentication & XAI Gate Security (Phase 3B.2)
    DELIVERY_AUTH_TOKEN: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Cryptographic shared secret for production delivery confirmation. Loaded from DELIVERY_AUTH_TOKEN env variable or .env file."
    )
    ALLOW_SIMULATED_DELIVERY: bool = True

    def is_simulation_permitted(self) -> bool:
        """Simulation is strictly disabled in production environments."""
        if self.ENVIRONMENT.lower() == "production":
            return False
        return self.ALLOW_SIMULATED_DELIVERY


settings = Settings()



