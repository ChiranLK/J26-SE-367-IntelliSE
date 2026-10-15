"""Local-only Ollama implementation of the Component 3 LLM interface."""

from __future__ import annotations

from json import JSONDecodeError
from time import perf_counter
from typing import Annotated, Any, Literal

import httpx
from fastapi import status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from intelise_c3.core.config import Settings
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.llm import (
    LLMGenerationParameters,
    LLMInferenceMetadata,
    LLMInferenceRequest,
    LLMInferenceResponse,
    OllamaResponseMetadata,
)


class _OllamaMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    role: Literal["assistant"]
    content: Annotated[str, Field(min_length=1)]

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Ollama returned empty assistant content.")
        return normalized


class _OllamaModelInfo(BaseModel):
    """Minimum `/api/show` fields needed to reject remote model proxies."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    details: dict[str, Any]
    remote_model: str | None = None
    remote_host: str | None = None


class _OllamaChatResponse(BaseModel):
    """Required and optional fields from a non-streaming `/api/chat` response."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    model: Annotated[str, Field(min_length=1)]
    created_at: Annotated[str, Field(min_length=1)]
    message: _OllamaMessage
    done: Literal[True]
    done_reason: str | None = None
    remote_model: str | None = None
    remote_host: str | None = None
    total_duration: Annotated[int | None, Field(ge=0)] = None
    load_duration: Annotated[int | None, Field(ge=0)] = None
    prompt_eval_count: Annotated[int | None, Field(ge=0)] = None
    prompt_eval_duration: Annotated[int | None, Field(ge=0)] = None
    eval_count: Annotated[int | None, Field(ge=0)] = None
    eval_duration: Annotated[int | None, Field(ge=0)] = None


class OllamaLLMClient:
    """Call only the configured loopback Ollama server; never fall back."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    async def generate(
        self, request: LLMInferenceRequest
    ) -> LLMInferenceResponse:
        """Submit a structured non-streaming chat request to local Ollama."""
        payload: dict[str, Any] = {
            "model": self._settings.ollama_model,
            "messages": [message.model_dump() for message in request.messages],
            "stream": False,
            "options": {
                "temperature": self._settings.ollama_temperature,
                "num_ctx": self._settings.ollama_num_ctx,
            },
        }
        if request.structured_output_schema is not None:
            payload["format"] = request.structured_output_schema
        endpoint = (
            f"{str(self._settings.ollama_base_url).rstrip('/')}/api/chat"
        )
        model_info_endpoint = (
            f"{str(self._settings.ollama_base_url).rstrip('/')}/api/show"
        )
        started_at = perf_counter()

        try:
            if self._http_client is None:
                async with httpx.AsyncClient() as client:
                    model_info_response = await client.post(
                        model_info_endpoint,
                        json={"model": self._settings.ollama_model},
                        timeout=self._settings.ollama_timeout_seconds,
                    )
                    self._validate_local_model(model_info_response)
                    response = await client.post(
                        endpoint,
                        json=payload,
                        timeout=self._settings.ollama_timeout_seconds,
                    )
            else:
                model_info_response = await self._http_client.post(
                    model_info_endpoint,
                    json={"model": self._settings.ollama_model},
                    timeout=self._settings.ollama_timeout_seconds,
                )
                self._validate_local_model(model_info_response)
                response = await self._http_client.post(
                    endpoint,
                    json=payload,
                    timeout=self._settings.ollama_timeout_seconds,
                )
        except httpx.TimeoutException as exception:
            raise self._application_error(
                "OLLAMA_REQUEST_TIMEOUT",
                "Local Ollama inference exceeded the configured timeout.",
                status.HTTP_504_GATEWAY_TIMEOUT,
            ) from exception
        except (httpx.ConnectError, httpx.NetworkError) as exception:
            raise self._application_error(
                "OLLAMA_SERVICE_UNAVAILABLE",
                (
                    "The local Ollama service is unavailable on the configured "
                    "loopback endpoint."
                ),
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exception
        except httpx.RequestError as exception:
            raise self._application_error(
                "OLLAMA_SERVICE_UNAVAILABLE",
                "The local Ollama request could not be completed.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exception

        latency_ms = round((perf_counter() - started_at) * 1000, 3)
        self._raise_for_http_error(response)

        try:
            parsed = _OllamaChatResponse.model_validate(response.json())
        except (JSONDecodeError, ValidationError, ValueError) as exception:
            raise self._application_error(
                "OLLAMA_INVALID_RESPONSE",
                "Ollama returned malformed, incomplete, or empty model output.",
                status.HTTP_502_BAD_GATEWAY,
            ) from exception

        if parsed.remote_model or parsed.remote_host:
            raise self._cloud_model_error()

        return LLMInferenceResponse(
            output_text=parsed.message.content,
            metadata=LLMInferenceMetadata(
                configured_model_identifier=self._settings.ollama_model,
                response_model_identifier=parsed.model,
                prompt_template_version=request.prompt_template_version,
                generation_parameters=LLMGenerationParameters(
                    temperature=self._settings.ollama_temperature,
                    num_ctx=self._settings.ollama_num_ctx,
                    timeout_seconds=self._settings.ollama_timeout_seconds,
                ),
                client_inference_latency_ms=latency_ms,
                response=OllamaResponseMetadata(
                    created_at=parsed.created_at,
                    done=parsed.done,
                    done_reason=parsed.done_reason,
                    total_duration_ns=parsed.total_duration,
                    load_duration_ns=parsed.load_duration,
                    prompt_eval_count=parsed.prompt_eval_count,
                    prompt_eval_duration_ns=parsed.prompt_eval_duration,
                    eval_count=parsed.eval_count,
                    eval_duration_ns=parsed.eval_duration,
                ),
            ),
        )

    def _validate_local_model(self, response: httpx.Response) -> None:
        self._raise_for_http_error(response)
        try:
            model_info = _OllamaModelInfo.model_validate(response.json())
        except (JSONDecodeError, ValidationError, ValueError) as exception:
            raise self._application_error(
                "OLLAMA_INVALID_MODEL_METADATA",
                "Ollama returned malformed or incomplete local model metadata.",
                status.HTTP_502_BAD_GATEWAY,
            ) from exception
        if model_info.remote_model or model_info.remote_host:
            raise self._cloud_model_error()

    @staticmethod
    def _cloud_model_error() -> ApplicationError:
        return OllamaLLMClient._application_error(
            "OLLAMA_CLOUD_MODEL_REJECTED",
            (
                "The configured Ollama model resolves to remote inference, "
                "which is forbidden."
            ),
            status.HTTP_400_BAD_REQUEST,
        )

    def _raise_for_http_error(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        if response.status_code == status.HTTP_404_NOT_FOUND:
            error_message = self._safe_error_message(response).lower()
            if "model" in error_message and (
                "not found" in error_message or "does not exist" in error_message
            ):
                raise self._application_error(
                    "OLLAMA_MODEL_NOT_INSTALLED",
                    (
                        f"The configured local Ollama model "
                        f"'{self._settings.ollama_model}' is not installed."
                    ),
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        raise self._application_error(
            "OLLAMA_UNEXPECTED_HTTP_RESPONSE",
            f"Ollama returned unexpected HTTP status {response.status_code}.",
            status.HTTP_502_BAD_GATEWAY,
        )

    @staticmethod
    def _safe_error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
        except (JSONDecodeError, ValueError):
            return ""
        if isinstance(body, dict) and isinstance(body.get("error"), str):
            return body["error"]
        return ""

    @staticmethod
    def _application_error(
        code: str, message: str, status_code: int
    ) -> ApplicationError:
        return ApplicationError(
            [ErrorDetail(code=code, field="ollama", message=message)],
            status_code=status_code,
        )
