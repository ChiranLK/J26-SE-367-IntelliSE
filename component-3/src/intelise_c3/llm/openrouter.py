"""Experimental OpenRouter adapter implementing the Component 3 LLMClient protocol.

OpenRouter exposes an OpenAI-compatible ``POST /chat/completions`` API in front of
many model providers. Like the TeamSocLo adapter, this client is explicitly
invoked only: it is never an automatic fallback for local Ollama and is not used
by the default research endpoint. The API key comes from the backend environment
and is sent only in the ``Authorization`` header; it never appears in errors,
logs or evidence.
"""

from __future__ import annotations

from json import JSONDecodeError
from time import perf_counter
from typing import Any

import httpx
from fastapi import status

from intelise_c3.core.config import Settings
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.llm import (
    LLMGenerationParameters,
    LLMInferenceMetadata,
    LLMInferenceRequest,
    LLMInferenceResponse,
    OpenRouterResponseMetadata,
)

OPENROUTER_MAX_TOKENS = 4096
#: Error codes for an answer without usable text; callers may treat them as a failed attempt.
OPENROUTER_EMPTY_CONTENT = "OPENROUTER_EMPTY_CONTENT"
OPENROUTER_OUTPUT_TRUNCATED = "OPENROUTER_OUTPUT_TRUNCATED"
OPENROUTER_RETRYABLE_CODES = frozenset({OPENROUTER_EMPTY_CONTENT, OPENROUTER_OUTPUT_TRUNCATED})


class OpenRouterLLMClient:
    """Explicitly invoked experimental client for the OpenRouter chat completions API."""

    def __init__(
        self,
        settings: Settings,
        *,
        temperature: float = 0.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._temperature = temperature
        self._http_client = http_client

    async def generate(self, request: LLMInferenceRequest) -> LLMInferenceResponse:
        key = (self._settings.openrouter_api_key or "").strip()
        if not key:
            raise self._application_error(
                "OPENROUTER_API_KEY_MISSING",
                "OpenRouter API key is not configured in the backend settings (OPENROUTER_API_KEY).",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        model = self._settings.openrouter_model
        max_tokens = getattr(self._settings, "openrouter_max_tokens", OPENROUTER_MAX_TOKENS)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": self._temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        reasoning_effort = getattr(self._settings, "openrouter_reasoning_effort", "omit")
        if reasoning_effort != "omit":
            payload["reasoning_effort"] = reasoning_effort
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Title": self._settings.openrouter_app_title,
        }
        referer = (self._settings.openrouter_http_referer or "").strip()
        if referer:
            headers["HTTP-Referer"] = referer
        endpoint = f"{str(self._settings.openrouter_base_url).rstrip('/')}/chat/completions"
        timeout = self._settings.openrouter_timeout_seconds
        started_at = perf_counter()
        try:
            if self._http_client is None:
                async with httpx.AsyncClient() as client:
                    response = await client.post(endpoint, json=payload, headers=headers, timeout=timeout)
            else:
                response = await self._http_client.post(endpoint, json=payload, headers=headers, timeout=timeout)
        except httpx.TimeoutException as exception:
            raise self._application_error(
                "OPENROUTER_REQUEST_TIMEOUT",
                "OpenRouter inference exceeded the configured timeout.",
                status.HTTP_504_GATEWAY_TIMEOUT,
            ) from exception
        except httpx.RequestError as exception:
            raise self._application_error(
                "OPENROUTER_SERVICE_UNAVAILABLE",
                "The OpenRouter API is unreachable or unavailable.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exception

        latency_ms = round((perf_counter() - started_at) * 1000, 3)
        self._raise_for_http_error(response)
        try:
            body = response.json()
        except (JSONDecodeError, ValueError) as exception:
            raise self._application_error(
                "OPENROUTER_INVALID_RESPONSE",
                "OpenRouter returned a malformed JSON response.",
                status.HTTP_502_BAD_GATEWAY,
            ) from exception
        if not isinstance(body, dict):
            raise self._application_error(
                "OPENROUTER_INVALID_RESPONSE",
                "OpenRouter returned an unexpected response shape.",
                status.HTTP_502_BAD_GATEWAY,
            )
        # OpenRouter can return HTTP 200 with an error object (e.g. upstream provider failure).
        if isinstance(body.get("error"), dict):
            code = body["error"].get("code")
            raise self._application_error(
                "OPENROUTER_UPSTREAM_ERROR",
                f"OpenRouter reported an upstream error{f' ({code})' if code is not None else ''}.",
                status.HTTP_502_BAD_GATEWAY,
            )

        choice = (body.get("choices") or [None])[0]
        text = self._extract_text(choice)
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        if not text:
            # Static, model-text-free diagnostics so an empty answer can be understood and repaired.
            finish = choice.get("finish_reason") if isinstance(choice, dict) else None
            native = choice.get("native_finish_reason") if isinstance(choice, dict) else None
            details = usage.get("completion_tokens_details")
            reasoning_tokens = details.get("reasoning_tokens") if isinstance(details, dict) else None
            facts = (
                f"finish_reason={finish}, native_finish_reason={native}, "
                f"completion_tokens={usage.get('completion_tokens')}, reasoning_tokens={reasoning_tokens}, "
                f"max_tokens={max_tokens}, answered_by={body.get('model') or model}"
            )
            if finish == "length":
                raise self._application_error(
                    OPENROUTER_OUTPUT_TRUNCATED,
                    f"OpenRouter stopped at the output limit before any answer text ({facts}); "
                    "reasoning tokens count toward max_tokens.",
                    status.HTTP_502_BAD_GATEWAY,
                )
            raise self._application_error(
                OPENROUTER_EMPTY_CONTENT,
                f"OpenRouter returned empty or non-text completion content ({facts}).",
                status.HTTP_502_BAD_GATEWAY,
            )
        response_model = str(body.get("model") or model)
        return LLMInferenceResponse(
            output_text=text,
            metadata=LLMInferenceMetadata(
                provider="openrouter",
                configured_model_identifier=model,
                response_model_identifier=response_model,
                prompt_template_version=request.prompt_template_version,
                generation_parameters=LLMGenerationParameters(
                    temperature=self._temperature,
                    timeout_seconds=timeout,
                    max_tokens=max_tokens,
                ),
                client_inference_latency_ms=latency_ms,
                response=OpenRouterResponseMetadata(
                    id=body.get("id"),
                    model=response_model,
                    upstream_provider=body.get("provider"),
                    finish_reason=choice.get("finish_reason") if isinstance(choice, dict) else None,
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                ),
            ),
        )

    @staticmethod
    def _extract_text(choice: Any) -> str:
        if not isinstance(choice, dict):
            return ""
        message = choice.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):  # content parts
            return "".join(
                part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"
            ).strip()
        return ""

    def _raise_for_http_error(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        code = response.status_code
        if code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
            raise self._application_error(
                "OPENROUTER_AUTHENTICATION_FAILED",
                "OpenRouter rejected the configured API key.",
                status.HTTP_502_BAD_GATEWAY,
            )
        if code == status.HTTP_402_PAYMENT_REQUIRED:
            raise self._application_error(
                "OPENROUTER_INSUFFICIENT_CREDITS",
                "The OpenRouter account has insufficient credits for this request.",
                status.HTTP_502_BAD_GATEWAY,
            )
        if code == status.HTTP_429_TOO_MANY_REQUESTS:
            raise self._application_error(
                "OPENROUTER_RATE_LIMITED",
                "OpenRouter request rate limit exceeded.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if code in (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND):
            raise self._application_error(
                "OPENROUTER_MODEL_OR_REQUEST_INVALID",
                f"OpenRouter rejected the request for model '{self._settings.openrouter_model}' (HTTP {code}).",
                status.HTTP_502_BAD_GATEWAY,
            )
        raise self._application_error(
            "OPENROUTER_GATEWAY_ERROR",
            f"OpenRouter returned unexpected HTTP status {code}.",
            status.HTTP_502_BAD_GATEWAY,
        )

    @staticmethod
    def _application_error(code: str, message: str, status_code: int) -> ApplicationError:
        return ApplicationError(
            [ErrorDetail(code=code, field="openrouter", message=message)],
            status_code=status_code,
        )
