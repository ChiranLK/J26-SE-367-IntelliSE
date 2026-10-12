"""Mocked tests for the local-only Ollama inference client."""

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from intelise_c3.core.config import Settings
from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.llm import LLMInferenceRequest, LLMMessage
from intelise_c3.llm.client import LLMClient
from intelise_c3.llm.ollama import OllamaLLMClient

Handler = Callable[[httpx.Request], httpx.Response]


def _settings(**updates: object) -> Settings:
    values: dict[str, object] = {
        "ollama_base_url": "http://127.0.0.1:11434",
        "ollama_model": "qwen2.5-coder:3b",
        "ollama_timeout_seconds": 30.0,
        "ollama_temperature": 0.0,
        "ollama_num_ctx": 4096,
        "_env_file": None,
    }
    values.update(updates)
    return Settings(**values)


def _request() -> LLMInferenceRequest:
    return LLMInferenceRequest(
        prompt_template_version="test-template-v1",
        messages=(
            LLMMessage(role="system", content="Use the test contract."),
            LLMMessage(role="user", content="Return a deterministic result."),
        ),
    )


def _valid_response(**updates: object) -> dict[str, object]:
    response: dict[str, object] = {
        "model": "qwen2.5-coder:3b",
        "created_at": "2026-10-13T00:00:00Z",
        "message": {"role": "assistant", "content": "validated result"},
        "done": True,
        "done_reason": "stop",
        "total_duration": 2_000_000,
        "load_duration": 100_000,
        "prompt_eval_count": 14,
        "prompt_eval_duration": 500_000,
        "eval_count": 3,
        "eval_duration": 1_000_000,
    }
    response.update(updates)
    return response


def _run_with_handler(
    handler: Handler,
    *,
    model_info_handler: Handler | None = None,
):
    async def invoke():
        def routed_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/show":
                assert json.loads(request.content) == {
                    "model": "qwen2.5-coder:3b"
                }
                if model_info_handler is not None:
                    return model_info_handler(request)
                return httpx.Response(
                    200,
                    json={
                        "details": {
                            "format": "gguf",
                            "parameter_size": "3B",
                        }
                    },
                )
            return handler(request)

        transport = httpx.MockTransport(routed_handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = OllamaLLMClient(_settings(), http_client=http_client)
            assert isinstance(client, LLMClient)
            return await client.generate(_request())

    return asyncio.run(invoke())


def test_successful_response_uses_structured_local_chat_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://127.0.0.1:11434/api/chat"
        payload = json.loads(request.content)
        assert payload == {
            "model": "qwen2.5-coder:3b",
            "messages": [
                {"role": "system", "content": "Use the test contract."},
                {
                    "role": "user",
                    "content": "Return a deterministic result.",
                },
            ],
            "stream": False,
            "options": {"temperature": 0.0, "num_ctx": 4096},
        }
        return httpx.Response(200, json=_valid_response())

    result = _run_with_handler(handler)

    assert result.output_text == "validated result"
    assert result.metadata.provider == "ollama-local"
    assert result.metadata.configured_model_identifier == "qwen2.5-coder:3b"
    assert result.metadata.response_model_identifier == "qwen2.5-coder:3b"
    assert result.metadata.prompt_template_version == "test-template-v1"
    assert result.metadata.generation_parameters.temperature == 0.0
    assert result.metadata.generation_parameters.num_ctx == 4096
    assert result.metadata.generation_parameters.timeout_seconds == 30.0
    assert result.metadata.client_inference_latency_ms >= 0.0
    assert result.metadata.response.done_reason == "stop"
    assert result.metadata.response.total_duration_ns == 2_000_000
    assert result.metadata.response.prompt_eval_count == 14
    assert result.metadata.response.eval_count == 3


@pytest.mark.parametrize(
    "response_body",
    (
        _valid_response(message={"role": "assistant", "content": ""}),
        _valid_response(message={"role": "assistant"}),
        _valid_response(done=False),
        {"error": "not a chat response"},
    ),
)
def test_empty_or_malformed_model_response_is_rejected(
    response_body: dict[str, object],
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_body)

    with pytest.raises(ApplicationError) as captured:
        _run_with_handler(handler)

    assert captured.value.status_code == 502
    assert captured.value.errors[0].code == "OLLAMA_INVALID_RESPONSE"


def test_non_json_model_response_is_rejected() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    with pytest.raises(ApplicationError) as captured:
        _run_with_handler(handler)

    assert captured.value.status_code == 502
    assert captured.value.errors[0].code == "OLLAMA_INVALID_RESPONSE"


def test_missing_local_model_is_reported() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"error": "model 'qwen2.5-coder:3b' not found"},
        )

    with pytest.raises(ApplicationError) as captured:
        _run_with_handler(handler)

    assert captured.value.status_code == 503
    assert captured.value.errors[0].code == "OLLAMA_MODEL_NOT_INSTALLED"


def test_unavailable_local_server_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ApplicationError) as captured:
        _run_with_handler(handler)

    assert captured.value.status_code == 503
    assert captured.value.errors[0].code == "OLLAMA_SERVICE_UNAVAILABLE"


def test_request_timeout_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(ApplicationError) as captured:
        _run_with_handler(handler)

    assert captured.value.status_code == 504
    assert captured.value.errors[0].code == "OLLAMA_REQUEST_TIMEOUT"


def test_unexpected_http_response_is_reported_without_body_leakage() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"error": "sensitive upstream diagnostic"},
        )

    with pytest.raises(ApplicationError) as captured:
        _run_with_handler(handler)

    error = captured.value.errors[0]
    assert captured.value.status_code == 502
    assert error.code == "OLLAMA_UNEXPECTED_HTTP_RESPONSE"
    assert "sensitive upstream diagnostic" not in error.message


def test_remote_model_metadata_is_rejected_before_chat() -> None:
    chat_was_called = False

    def chat_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal chat_was_called
        chat_was_called = True
        return httpx.Response(200, json=_valid_response())

    def remote_model_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "details": {"format": "remote"},
                "remote_model": "provider/model",
                "remote_host": "https://ollama.com",
            },
        )

    with pytest.raises(ApplicationError) as captured:
        _run_with_handler(
            chat_handler,
            model_info_handler=remote_model_handler,
        )

    assert captured.value.status_code == 400
    assert captured.value.errors[0].code == "OLLAMA_CLOUD_MODEL_REJECTED"
    assert chat_was_called is False


def test_malformed_model_metadata_is_rejected_before_chat() -> None:
    def chat_handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("Chat must not run when model metadata is invalid.")

    def malformed_model_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    with pytest.raises(ApplicationError) as captured:
        _run_with_handler(
            chat_handler,
            model_info_handler=malformed_model_handler,
        )

    assert captured.value.status_code == 502
    assert captured.value.errors[0].code == "OLLAMA_INVALID_MODEL_METADATA"
