"""Experimental TeamSocLo Claude adapter implementing the Component 3 LLMClient protocol."""

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
    TeamSocLoResponseMetadata,
)


class TeamSocLoClaudeLLMClient:
    """Explicitly invoked experimental Claude client via TeamSocLo gateway.

    This client is strictly isolated from the official local Ollama runtime.
    It is never called as an automatic fallback and never exposed in the default
    research generation endpoints.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    async def generate(self, request: LLMInferenceRequest) -> LLMInferenceResponse:
        """Submit a structured non-streaming request to TeamSocLo Claude."""
        if not self._settings.teamsoclo_api_key or not self._settings.teamsoclo_api_key.strip():
            raise self._application_error(
                "TEAMSOCLO_API_KEY_MISSING",
                "TeamSocLo API key is not configured in backend settings.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        model = self._normalize_model(self._settings.teamsoclo_model)

        system_parts = [
            message.content for message in request.messages if message.role == "system"
        ]
        system_text = "\n\n".join(system_parts) if system_parts else None

        anthropic_messages = [
            {"role": message.role, "content": message.content}
            for message in request.messages
            if message.role in {"user", "assistant"}
        ]
        if not anthropic_messages:
            raise self._application_error(
                "TEAMSOCLO_INVALID_REQUEST",
                "TeamSocLo Claude requires at least one user or assistant message.",
                status.HTTP_400_BAD_REQUEST,
            )

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": getattr(self._settings, "teamsoclo_max_tokens", 4096),
            "temperature": 0.0,
            "messages": anthropic_messages,
        }
        if system_text:
            payload["system"] = system_text

        endpoint = f"{str(self._settings.teamsoclo_base_url).rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": self._settings.teamsoclo_api_key.strip(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        started_at = perf_counter()

        try:
            if self._http_client is None:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        endpoint,
                        json=payload,
                        headers=headers,
                        timeout=self._settings.teamsoclo_timeout_seconds,
                    )
            else:
                response = await self._http_client.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self._settings.teamsoclo_timeout_seconds,
                )
        except httpx.TimeoutException as exception:
            raise self._application_error(
                "TEAMSOCLO_REQUEST_TIMEOUT",
                "TeamSocLo Claude inference exceeded the configured timeout.",
                status.HTTP_504_GATEWAY_TIMEOUT,
            ) from exception
        except (httpx.ConnectError, httpx.NetworkError) as exception:
            raise self._application_error(
                "TEAMSOCLO_SERVICE_UNAVAILABLE",
                "The TeamSocLo gateway is unreachable or unavailable.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exception
        except httpx.RequestError as exception:
            raise self._application_error(
                "TEAMSOCLO_SERVICE_UNAVAILABLE",
                "The TeamSocLo Claude request could not be completed.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exception

        latency_ms = round((perf_counter() - started_at) * 1000, 3)
        self._raise_for_http_error(response)

        try:
            body = response.json()
        except (JSONDecodeError, ValueError) as exception:
            raise self._application_error(
                "TEAMSOCLO_INVALID_RESPONSE",
                "TeamSocLo returned malformed JSON response "
                f"(HTTP {response.status_code}, content-type {response.headers.get('content-type', '?')}, {len(response.content)} bytes).",
                status.HTTP_502_BAD_GATEWAY,
            ) from exception

        text_content = self._extract_text_content(body)
        if not text_content:
            # Safe diagnostics only: structure and counters, never model text.
            blocks = [b.get("type") for b in body.get("content", []) if isinstance(b, dict)] if isinstance(body.get("content"), list) else type(body.get("content")).__name__
            usage_hint = body.get("usage") if isinstance(body.get("usage"), dict) else {}
            raise self._application_error(
                "TEAMSOCLO_INVALID_RESPONSE",
                "TeamSocLo returned empty or non-text response content "
                f"(stop_reason={body.get('stop_reason')}, content blocks={blocks}, "
                f"output_tokens={usage_hint.get('output_tokens')}, body type={body.get('type')}, "
                f"answered_by={body.get('model')}).",
                status.HTTP_502_BAD_GATEWAY,
            )

        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        total_tokens = (
            (input_tokens or 0) + (output_tokens or 0)
            if (input_tokens is not None or output_tokens is not None)
            else None
        )

        response_model = body.get("model") or model
        metadata = LLMInferenceMetadata(
            provider="teamsoclo-claude",
            configured_model_identifier=self._settings.teamsoclo_model,
            response_model_identifier=str(response_model),
            prompt_template_version=request.prompt_template_version,
            generation_parameters=LLMGenerationParameters(
                temperature=0.0,
                timeout_seconds=self._settings.teamsoclo_timeout_seconds,
                max_tokens=getattr(self._settings, "teamsoclo_max_tokens", 4096),
            ),
            client_inference_latency_ms=latency_ms,
            response=TeamSocLoResponseMetadata(
                id=body.get("id"),
                model=str(response_model),
                stop_reason=body.get("stop_reason"),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            ),
        )

        return LLMInferenceResponse(
            output_text=text_content,
            metadata=metadata,
        )

    @staticmethod
    def _normalize_model(model_identifier: str) -> str:
        normalized = model_identifier.strip()
        lower = normalized.lower()
        if lower in {"haiku-4.5", "claude-haiku-4.5", "claude-haiku-4-5"}:
            return "claude-haiku-4-5"
        return normalized

    @staticmethod
    def _extract_text_content(body: dict[str, Any]) -> str:
        """Extract text blocks while ignoring internal thinking blocks."""
        raw_content = body.get("content")
        if isinstance(raw_content, str):
            return raw_content.strip()
        if isinstance(raw_content, list):
            text_blocks: list[str] = []
            for block in raw_content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        text_blocks.append(text)
            return "".join(text_blocks).strip()
        return ""

    def _raise_for_http_error(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            raise self._application_error(
                "TEAMSOCLO_AUTHENTICATION_FAILED",
                "TeamSocLo gateway rejected the configured credentials.",
                status.HTTP_502_BAD_GATEWAY,
            )
        if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            raise self._application_error(
                "TEAMSOCLO_RATE_LIMITED",
                "TeamSocLo request rate limit exceeded.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if response.status_code == status.HTTP_404_NOT_FOUND:
            raise self._application_error(
                "TEAMSOCLO_MODEL_NOT_FOUND",
                f"Configured model '{self._settings.teamsoclo_model}' was not found on TeamSocLo gateway.",
                status.HTTP_502_BAD_GATEWAY,
            )
        raise self._application_error(
            "TEAMSOCLO_GATEWAY_ERROR",
            f"TeamSocLo gateway returned unexpected HTTP status {response.status_code}.",
            status.HTTP_502_BAD_GATEWAY,
        )

    @staticmethod
    def _application_error(
        code: str, message: str, status_code: int
    ) -> ApplicationError:
        return ApplicationError(
            [ErrorDetail(code=code, field="teamsoclo", message=message)],
            status_code=status_code,
        )
