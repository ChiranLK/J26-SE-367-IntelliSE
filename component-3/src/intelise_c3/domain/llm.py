"""Immutable local-LLM requests, responses, and reproducibility metadata."""

from typing import Annotated, Any, Literal

from pydantic import Field, field_validator

from intelise_c3.domain.generation_context import DomainModel


class LLMMessage(DomainModel):
    """One explicit message sent to a local inference client."""

    role: Literal["system", "user", "assistant"]
    content: Annotated[str, Field(min_length=1)]

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("LLM message content must not be blank.")
        return normalized


class LLMInferenceRequest(DomainModel):
    """Provider-neutral input for future C3 generation agents."""

    messages: Annotated[tuple[LLMMessage, ...], Field(min_length=1)]
    prompt_template_version: Annotated[str, Field(min_length=1)]
    structured_output_schema: dict[str, Any] | None = None

    @field_validator("prompt_template_version")
    @classmethod
    def reject_blank_template_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Prompt template version must not be blank.")
        return normalized


class LLMGenerationParameters(DomainModel):
    """Effective parameters recorded with each inference result."""

    temperature: float
    num_ctx: int | None = None
    timeout_seconds: float
    max_tokens: int | None = None


class OllamaResponseMetadata(DomainModel):
    """Non-sensitive response statistics returned by Ollama when available."""

    created_at: str
    done: bool
    done_reason: str | None = None
    total_duration_ns: int | None = None
    load_duration_ns: int | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration_ns: int | None = None
    eval_count: int | None = None
    eval_duration_ns: int | None = None


class TeamSocLoResponseMetadata(DomainModel):
    """Non-sensitive response statistics returned by TeamSocLo Claude gateway."""

    id: str | None = None
    model: str
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class OpenRouterResponseMetadata(DomainModel):
    """Non-sensitive response statistics returned by the OpenRouter API."""

    id: str | None = None
    model: str
    upstream_provider: str | None = None
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMInferenceMetadata(DomainModel):
    """Reproducibility record for an LLM inference request."""

    provider: Literal["ollama-local", "teamsoclo-claude", "openrouter"] = "ollama-local"
    configured_model_identifier: str
    response_model_identifier: str
    prompt_template_version: str
    generation_parameters: LLMGenerationParameters
    client_inference_latency_ms: float
    response: OllamaResponseMetadata | TeamSocLoResponseMetadata | OpenRouterResponseMetadata


class LLMInferenceResponse(DomainModel):
    """Validated text and metadata returned by an LLM client."""

    output_text: str
    metadata: LLMInferenceMetadata
