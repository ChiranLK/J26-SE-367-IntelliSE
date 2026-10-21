"""OpenRouter experimental provider: client, configuration, gates and generation evidence."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from intelise_c3.contracts.generation import GenerationMode
from intelise_c3.core.config import Settings
from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.generation import ArtifactOrigin
from intelise_c3.domain.llm import LLMInferenceRequest, LLMMessage
from intelise_c3.generation.evidence import verify_manifest_evidence
from intelise_c3.generation.templates import template_task_service
from intelise_c3.llm.openrouter import OpenRouterLLMClient
from intelise_c3.main import create_app
from intelise_c3.services.code_generation import CodeGenerationService

from tests.test_claude_experiment import _build_request

FAKE_KEY = "sk-or-test-not-a-real-key-0000"
PROMPT = LLMInferenceRequest(
    prompt_template_version="test-prompt-v1",
    messages=(LLMMessage(role="system", content="You write code."), LLMMessage(role="user", content="Say hi.")),
)


def _settings(**overrides) -> Settings:
    values = {"openrouter_api_key": FAKE_KEY, "openrouter_model": "openai/gpt-4o", **overrides}
    return Settings(**values, _env_file=None)


def _client(handler, *, temperature: float = 0.0, **overrides) -> OpenRouterLLMClient:
    return OpenRouterLLMClient(
        _settings(**overrides),
        temperature=temperature,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _completion(content="hello", **extra) -> dict:
    body = {
        "id": "gen-123",
        "model": "openai/gpt-4o-2024-08-06",
        "provider": "OpenAI",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
    }
    body.update(extra)
    return body


@pytest.mark.anyio
async def test_sends_an_openai_compatible_request_and_records_provider_evidence() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion())

    result = await _client(handler, temperature=0.3).generate(PROMPT)

    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["headers"]["authorization"] == f"Bearer {FAKE_KEY}"
    assert seen["headers"]["x-title"] == "InteliSE Component 3"
    assert "http-referer" not in seen["headers"]
    assert seen["body"]["model"] == "openai/gpt-4o"
    assert seen["body"]["temperature"] == 0.3
    assert seen["body"]["max_tokens"] == 4096
    assert "reasoning_effort" not in seen["body"]
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]
    assert result.output_text == "hello"
    meta = result.metadata
    assert meta.provider == "openrouter"
    assert meta.configured_model_identifier == "openai/gpt-4o"
    assert meta.response_model_identifier == "openai/gpt-4o-2024-08-06"  # the model OpenRouter actually used
    assert meta.response.upstream_provider == "OpenAI"
    assert meta.response.total_tokens == 15
    assert FAKE_KEY not in meta.model_dump_json()  # the key never enters evidence


@pytest.mark.anyio
async def test_optional_referer_header_and_content_parts() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["referer"] = request.headers.get("http-referer")
        return httpx.Response(200, json=_completion([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]))

    result = await _client(handler, openrouter_http_referer="https://intelise.example").generate(PROMPT)
    assert seen["referer"] == "https://intelise.example"
    assert result.output_text == "ab"


@pytest.mark.anyio
async def test_missing_key_fails_before_any_network_call() -> None:
    def handler(_request):  # pragma: no cover - must not be called
        raise AssertionError("no request may be sent without a key")

    with pytest.raises(ApplicationError) as error:
        await _client(handler, openrouter_api_key=None).generate(PROMPT)
    assert error.value.errors[0].code == "OPENROUTER_API_KEY_MISSING"
    assert error.value.status_code == 503


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (401, {"error": {"message": "bad key"}}, "OPENROUTER_AUTHENTICATION_FAILED"),
        (402, {"error": {"message": "no credits"}}, "OPENROUTER_INSUFFICIENT_CREDITS"),
        (429, {"error": {"message": "slow down"}}, "OPENROUTER_RATE_LIMITED"),
        (400, {"error": {"message": "bad model"}}, "OPENROUTER_MODEL_OR_REQUEST_INVALID"),
        (500, {"error": {"message": "boom"}}, "OPENROUTER_GATEWAY_ERROR"),
        (200, {"error": {"code": 502, "message": "upstream down"}}, "OPENROUTER_UPSTREAM_ERROR"),
        (200, _completion(""), "OPENROUTER_EMPTY_CONTENT"),
        (200, {**_completion(""), "choices": [{"finish_reason": "length", "message": {"role": "assistant", "content": ""}}]}, "OPENROUTER_OUTPUT_TRUNCATED"),
    ],
)
async def test_errors_are_mapped_without_leaking_the_key(status, body, code) -> None:
    with pytest.raises(ApplicationError) as error:
        await _client(lambda _r: httpx.Response(status, json=body)).generate(PROMPT)
    assert error.value.errors[0].code == code
    assert FAKE_KEY not in json.dumps([e.model_dump() for e in error.value.errors])


@pytest.mark.anyio
async def test_timeout_is_reported_as_504() -> None:
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ApplicationError) as error:
        await _client(handler).generate(PROMPT)
    assert error.value.errors[0].code == "OPENROUTER_REQUEST_TIMEOUT"
    assert error.value.status_code == 504


def test_base_url_must_be_https() -> None:
    with pytest.raises(ValidationError):
        Settings(openrouter_base_url="http://openrouter.ai/api/v1")
    # The default must be "disabled" regardless of the developer's own .env file.
    assert Settings(_env_file=None).openrouter_experiment_enabled is False


def test_default_endpoint_rejects_openrouter_mode() -> None:
    client = TestClient(create_app())
    request = _build_request("task_management", GenerationMode.EXPERIMENTAL_OPENROUTER)
    response = client.post("/api/v1/generation-runs", json=request.model_dump(mode="json"))
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "EXPERIMENTAL_MODE_REJECTED"


@pytest.mark.parametrize(
    "path", ["/api/v1/experiments/openrouter-generation", "/api/v1/behaviour/generation-runs"]
)
def test_openrouter_paths_are_forbidden_while_the_experiment_is_disabled(path) -> None:
    app = create_app()
    app.state.settings = Settings(openrouter_experiment_enabled=False)
    request = _build_request("task_management", GenerationMode.EXPERIMENTAL_OPENROUTER)
    response = TestClient(app).post(path, json=request.model_dump(mode="json"))
    assert response.status_code == 403
    assert response.json()["errors"][0]["code"] == "EXPERIMENT_DISABLED"


@pytest.mark.anyio
async def test_openrouter_generation_is_isolated_and_attributed(tmp_path: Path) -> None:
    service_text = json.dumps({"path": "backend/src/services/taskService.js", "content": template_task_service().content.strip()})
    client = _client(lambda _r: httpx.Response(200, json=_completion(service_text)))
    result = await CodeGenerationService(workspace_root=tmp_path, llm_client=client).generate(
        _build_request("task_management", GenerationMode.EXPERIMENTAL_OPENROUTER)
    )
    manifest = result.manifest
    assert result.workspace_relative_path.startswith("experiments/")
    assert manifest.generation_mode == GenerationMode.EXPERIMENTAL_OPENROUTER
    assert manifest.llm_inference.provider == "openrouter"
    assert manifest.llm_inference.response_model_identifier == "openai/gpt-4o-2024-08-06"
    record = next(f for f in manifest.files if f.relative_path == "backend/src/services/taskService.js")
    assert record.origin == ArtifactOrigin.EXPERIMENTAL_OPENROUTER
    assert verify_manifest_evidence(manifest)


def test_overview_reports_openrouter_configuration_without_the_key(monkeypatch) -> None:
    import intelise_c3.services.demo_support as demo_support

    monkeypatch.setattr(demo_support, "probe_ollama", lambda settings: demo_support.OllamaStatus(
        base_url="http://127.0.0.1:11434", configured_model="m", reachable=False, model_installed=None,
        detail="skipped", checked_at_utc="2026-10-20T00:00:00Z"))
    app = create_app()
    app.state.settings = _settings(openrouter_experiment_enabled=True)
    response = TestClient(app).get("/api/v1/demo/overview")
    assert response.status_code == 200
    assert response.json()["openrouter"] == {"enabled": True, "key_configured": True, "model": "openai/gpt-4o"}
    assert FAKE_KEY not in response.text


def test_connectivity_check_uses_a_fixed_prompt_and_reports_the_answering_model(monkeypatch) -> None:
    import intelise_c3.api.routes.experiments as experiments

    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion("OK"))

    monkeypatch.setattr(
        experiments,
        "OpenRouterLLMClient",
        lambda settings: OpenRouterLLMClient(settings, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))),
    )
    app = create_app()
    app.state.settings = _settings(openrouter_experiment_enabled=True)
    response = TestClient(app).post("/api/v1/experiments/openrouter-check")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True and body["reply"] == "OK"
    assert body["response_model"] == "openai/gpt-4o-2024-08-06"
    assert sent["body"]["messages"] == [{"role": "user", "content": "Reply with exactly the word OK."}]
    assert FAKE_KEY not in response.text


def test_connectivity_check_is_forbidden_while_disabled() -> None:
    app = create_app()
    app.state.settings = Settings(openrouter_experiment_enabled=False)
    response = TestClient(app).post("/api/v1/experiments/openrouter-check")
    assert response.status_code == 403


@pytest.mark.anyio
async def test_empty_answer_error_carries_static_diagnostics_but_no_model_text() -> None:
    body = {
        **_completion(""),
        "choices": [{"finish_reason": "length", "native_finish_reason": "length", "message": {"role": "assistant", "content": "", "reasoning": "SECRET-THOUGHTS"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 4096, "completion_tokens_details": {"reasoning_tokens": 4096}},
    }
    with pytest.raises(ApplicationError) as error:
        await _client(lambda _r: httpx.Response(200, json=body)).generate(PROMPT)
    message = error.value.errors[0].message
    assert "finish_reason=length" in message and "reasoning_tokens=4096" in message and "max_tokens=4096" in message
    assert "SECRET-THOUGHTS" not in message
