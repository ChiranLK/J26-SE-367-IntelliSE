"""Unit tests for the experimental TeamSocLo Claude LLM client using httpx mocks."""

import json
import pytest
import httpx

from intelise_c3.core.config import Settings
from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.llm import LLMInferenceRequest, LLMMessage
from intelise_c3.llm.teamsoclo import TeamSocLoClaudeLLMClient


def _make_settings(
    *,
    api_key: str | None = "mock-secret-key-12345",
    base_url: str = "https://gpt.teamsoclo.site",
    model: str = "claude-haiku-4-5",
    timeout: float = 30.0,
    experiment_enabled: bool = True,
) -> Settings:
    return Settings(
        teamsoclo_experiment_enabled=experiment_enabled,
        teamsoclo_api_key=api_key,
        teamsoclo_base_url=base_url,
        teamsoclo_model=model,
        teamsoclo_timeout_seconds=timeout,
    )


def _make_request(
    system_text: str = "You are a test assistant.",
    user_text: str = "Generate code.",
) -> LLMInferenceRequest:
    return LLMInferenceRequest(
        prompt_template_version="test-template-v1",
        messages=(
            LLMMessage(role="system", content=system_text),
            LLMMessage(role="user", content=user_text),
        ),
    )


@pytest.mark.anyio
async def test_successful_claude_generation():
    """Verify normal text generation and token extraction."""
    captured_request = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["headers"] = dict(request.headers)
        captured_request["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "id": "msg_test_123",
                "model": "claude-haiku-4-5",
                "role": "assistant",
                "content": [{"type": "text", "text": "export function test() {}"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 42, "output_tokens": 15},
            },
        )

    settings = _make_settings()
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TeamSocLoClaudeLLMClient(settings, http_client=http_client)
        response = await client.generate(_make_request())

    assert response.output_text == "export function test() {}"
    assert response.metadata.provider == "teamsoclo-claude"
    assert response.metadata.configured_model_identifier == "claude-haiku-4-5"
    assert response.metadata.response_model_identifier == "claude-haiku-4-5"
    assert response.metadata.response.id == "msg_test_123"
    assert response.metadata.response.input_tokens == 42
    assert response.metadata.response.output_tokens == 15
    assert response.metadata.response.total_tokens == 57

    # Verify Anthropic format
    assert captured_request["url"] == "https://gpt.teamsoclo.site/v1/messages"
    assert captured_request["headers"]["x-api-key"] == "mock-secret-key-12345"
    assert captured_request["headers"]["anthropic-version"] == "2023-06-01"
    assert captured_request["body"]["system"] == "You are a test assistant."
    assert captured_request["body"]["messages"] == [
        {"role": "user", "content": "Generate code."}
    ]


@pytest.mark.anyio
async def test_thinking_block_handling():
    """Verify thinking blocks are cleanly stripped and only text blocks returned."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "msg_thinking_456",
                "model": "claude-haiku-4-5",
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "Internal reasoning here..."},
                    {"type": "text", "text": "{\"path\": \"test.js\", \"content\": \"safe\"}"},
                ],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 50, "output_tokens": 30},
            },
        )

    settings = _make_settings()
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TeamSocLoClaudeLLMClient(settings, http_client=http_client)
        response = await client.generate(_make_request())

    assert response.output_text == "{\"path\": \"test.js\", \"content\": \"safe\"}"
    assert "thinking" not in response.output_text


@pytest.mark.anyio
async def test_model_normalization():
    """Verify 'Haiku-4.5' normalizes to 'claude-haiku-4-5'."""
    captured_body = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "id": "msg_norm_789",
                "model": "claude-haiku-4-5",
                "role": "assistant",
                "content": [{"type": "text", "text": "ok"}],
            },
        )

    settings = _make_settings(model="Haiku-4.5")
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TeamSocLoClaudeLLMClient(settings, http_client=http_client)
        await client.generate(_make_request())

    assert captured_body["model"] == "claude-haiku-4-5"


@pytest.mark.anyio
async def test_missing_api_key_raises():
    """Verify missing API key fails before making requests."""
    settings = _make_settings(api_key=None)
    client = TeamSocLoClaudeLLMClient(settings)
    with pytest.raises(ApplicationError) as exc_info:
        await client.generate(_make_request())

    assert exc_info.value.status_code == 503
    assert exc_info.value.errors[0].code == "TEAMSOCLO_API_KEY_MISSING"


@pytest.mark.anyio
async def test_unauthorized_401_raises_auth_failed():
    """Verify 401 raises TEAMSOCLO_AUTHENTICATION_FAILED (502)."""
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})

    settings = _make_settings()
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TeamSocLoClaudeLLMClient(settings, http_client=http_client)
        with pytest.raises(ApplicationError) as exc_info:
            await client.generate(_make_request())

    assert exc_info.value.status_code == 502
    assert exc_info.value.errors[0].code == "TEAMSOCLO_AUTHENTICATION_FAILED"


@pytest.mark.anyio
async def test_rate_limited_429():
    """Verify 429 raises TEAMSOCLO_RATE_LIMITED (429)."""
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}})

    settings = _make_settings()
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TeamSocLoClaudeLLMClient(settings, http_client=http_client)
        with pytest.raises(ApplicationError) as exc_info:
            await client.generate(_make_request())

    assert exc_info.value.status_code == 429
    assert exc_info.value.errors[0].code == "TEAMSOCLO_RATE_LIMITED"


@pytest.mark.anyio
async def test_timeout_raises_gateway_timeout():
    """Verify timeout raises TEAMSOCLO_REQUEST_TIMEOUT (504)."""
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Read timed out")

    settings = _make_settings()
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TeamSocLoClaudeLLMClient(settings, http_client=http_client)
        with pytest.raises(ApplicationError) as exc_info:
            await client.generate(_make_request())

    assert exc_info.value.status_code == 504
    assert exc_info.value.errors[0].code == "TEAMSOCLO_REQUEST_TIMEOUT"


@pytest.mark.anyio
async def test_connection_error_raises_service_unavailable():
    """Verify connection error raises TEAMSOCLO_SERVICE_UNAVAILABLE (503)."""
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    settings = _make_settings()
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TeamSocLoClaudeLLMClient(settings, http_client=http_client)
        with pytest.raises(ApplicationError) as exc_info:
            await client.generate(_make_request())

    assert exc_info.value.status_code == 503
    assert exc_info.value.errors[0].code == "TEAMSOCLO_SERVICE_UNAVAILABLE"


@pytest.mark.anyio
async def test_secret_is_never_leaked_in_errors():
    """Verify secret API key is never exposed in error messages or exceptions."""
    secret = "super-secret-key-xyz999"

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"Gateway error occurred with request header {request.headers.get('x-api-key')}")

    settings = _make_settings(api_key=secret)
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TeamSocLoClaudeLLMClient(settings, http_client=http_client)
        with pytest.raises(ApplicationError) as exc_info:
            await client.generate(_make_request())

    error_message = exc_info.value.errors[0].message
    assert secret not in error_message
    assert secret not in str(exc_info.value)
