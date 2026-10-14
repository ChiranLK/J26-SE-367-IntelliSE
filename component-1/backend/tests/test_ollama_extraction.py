"""Mocked Ollama regression tests; no claim about actual model accuracy."""
import asyncio
import json
from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import OperationFailure
from unittest.mock import AsyncMock

from intelise_c1.api.extraction_schemas import GeneratedOutput, OllamaQuotes
from intelise_c1.core.config import Settings
from intelise_c1.main import create_app
from intelise_c1.services.extraction import build_run, resolve_evidence, resolve_quotes, OLLAMA_SYSTEM_PROMPT
from intelise_c1.services.provider import OllamaProvider, AnthropicProvider, ProviderTimeout
from test_extractions import client, URL, ID

REAL_ASYNC_CLIENT = httpx.AsyncClient

DISCUSSION = ("Customers can book appointments. Only administrators can delete\n"
              "accounts. Search results must appear within two seconds.\nWe will meet on Friday.")
EXPECTED = ["Customers can book appointments.", "Only administrators can delete\naccounts.",
            "Search results must appear within two seconds."]


def generated(quotes=EXPECTED):
    return {"quotes": list(quotes)}


def envelope(data=None, **changes):
    return {"done": True, "done_reason": "stop", "message": {
        "role": "assistant", "content": json.dumps(generated() if data is None else data)}, **changes}


def mock_http(monkeypatch, handler):
    real_client = REAL_ASYNC_CLIENT
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs))


def use_ollama(client):
    client.app.state.projects.get.return_value.discussion_text = DISCUSSION
    client.app.state.extraction_provider = OllamaProvider(Settings(_env_file=None))


def test_observed_discussion_three_candidates_and_backend_offsets(client, monkeypatch):
    def handler(request):
        payload = json.loads(request.content)
        assert request.url == "http://localhost:11434/api/chat"
        assert payload["model"] == "llama3.2:1b"
        assert payload["stream"] is False
        assert payload["options"] == {"temperature": 0, "num_ctx": 2048, "num_predict": 256}
        assert payload["messages"][0] == {"role": "system", "content": OLLAMA_SYSTEM_PROMPT}
        assert json.loads(payload["messages"][1]["content"])["discussion_text"] == DISCUSSION
        assert payload["format"]["additionalProperties"] is False
        assert set(payload["format"]["properties"]) == {"quotes"}
        return httpx.Response(200, json=envelope())
    mock_http(monkeypatch, handler)
    use_ollama(client)
    response = client.post(URL)
    assert response.status_code == 201
    run = response.json()
    assert run["provider"] == "ollama" and run["model_identifier"] == "llama3.2:1b"
    assert [c["requirement_text"] for c in run["candidates"]] == EXPECTED
    assert "Friday" not in str(run["candidates"])
    assert run["prompt_version"] == "c1-ollama-quotes-v3"
    assert all(c["actor"] is None and c["action"] is None for c in run["candidates"])
    for c in run["candidates"]:
        span = c["evidence"][0]
        assert c["review_status"] == "unreviewed"
        assert DISCUSSION[span["start"]:span["end"]] == span["quote"] == c["requirement_text"]


@pytest.mark.parametrize("addition", ["Users must log in.", "Send appointment reminders.",
                                      "Support Windows and macOS.", "Show booking history."])
def test_unsupported_addition_fails_entire_run(client, monkeypatch, addition):
    mock_http(monkeypatch, lambda r: httpx.Response(200, json=envelope(generated(EXPECTED + [addition]))))
    use_ollama(client)
    assert client.post(URL).status_code == 502
    assert client.app.state.extractions.collection.documents == []


def test_fabricated_candidate_with_real_quote_still_rejected(client):
    data = {"candidates": [{"requirement_text": "Send appointment reminders.",
                           "evidence": [{"quote": EXPECTED[0]}], "actor": None, "action": None}]}
    client.app.state.projects.get.return_value.discussion_text = DISCUSSION
    client.app.state.extraction_provider.extract.return_value = resolve_evidence(
        DISCUSSION, GeneratedOutput.model_validate(data))
    assert client.post(URL).status_code == 502
    assert client.app.state.extractions.collection.documents == []


def test_malformed_friday_quote_rejects_whole_run_without_repair(client, monkeypatch):
    mock_http(monkeypatch, lambda r: httpx.Response(200, json=envelope()))
    use_ollama(client)
    saved = client.post(URL).json()
    original = deepcopy(client.app.state.extractions.collection.documents)
    mock_http(monkeypatch, lambda r: httpx.Response(200, json=envelope(
        generated(EXPECTED + ["We will meet onFriday."]))))
    response = client.post(URL)
    assert response.status_code == 502
    assert "absent from the original source" in response.json()["detail"]
    assert client.get(URL + "/latest").json() == saved
    assert client.app.state.extractions.collection.documents == original


def test_exact_friday_quote_is_traceable_but_irrelevant(client, monkeypatch):
    """Explicitly expose the relevance limitation; no semantic approval claim."""
    mock_http(monkeypatch, lambda r: httpx.Response(200, json=envelope(
        generated(EXPECTED + ["We will meet on Friday."]))))
    use_ollama(client)
    response = client.post(URL)
    assert response.status_code == 201  # Source checks alone cannot decide relevance.
    candidates = response.json()["candidates"]
    assert [c["requirement_text"] for c in candidates] != EXPECTED  # Fixture evaluation fails.
    friday = candidates[-1]
    assert friday["review_status"] == "unreviewed"
    span = friday["evidence"][0]
    assert DISCUSSION[span["start"]:span["end"]] == "We will meet on Friday."


@pytest.mark.parametrize("case,status", [
    ("unavailable", 503), ("missing_model", 503), ("timeout", 504),
    ("empty", 502), ("invalid_json", 502), ("invalid_schema", 502),
    ("truncated", 502), ("incomplete", 502), ("partial_json", 502),
    ("duplicate", 502), ("blank", 502), ("oversized", 502), ("missing_done", 502),
])
def test_failures_keep_successful_run_and_discussion(client, monkeypatch, case, status):
    mock_http(monkeypatch, lambda r: httpx.Response(200, json=envelope()))
    use_ollama(client)
    saved = client.post(URL).json()
    original = deepcopy(client.app.state.extractions.collection.documents)
    calls = []
    def handler(request):
        calls.append(request)
        message = envelope()
        if case == "unavailable":
            raise httpx.ConnectError("secret discussion")
        if case == "timeout":
            raise httpx.ReadTimeout("secret discussion")
        if case == "missing_model":
            return httpx.Response(404, json={"error": "secret discussion"})
        if case == "empty":
            message["message"]["content"] = " "
        if case == "invalid_json":
            return httpx.Response(200, text="secret discussion")
        if case == "invalid_schema":
            message["message"]["content"] = '{"candidates": [{}]}'
        if case == "truncated":
            message["done_reason"] = "length"
        if case == "incomplete":
            message["done"] = False
        if case == "partial_json":
            message["message"]["content"] = '{"candidates": ['
        if case == "duplicate":
            message = envelope(generated([EXPECTED[0], EXPECTED[0]]))
        if case == "blank":
            message = envelope(generated([" "]))
        if case == "oversized":
            return httpx.Response(200, content=b"x" * 262145)
        if case == "missing_done":
            message.pop("done")
        return httpx.Response(200, json=message)
    mock_http(monkeypatch, handler)
    response = client.post(URL)
    assert response.status_code == status
    assert len(calls) == 1  # No retry or fallback, including timeouts.
    assert "secret discussion" not in response.text and DISCUSSION not in response.text
    assert client.app.state.extractions.collection.documents == original
    assert client.get(URL + "/latest").json() == saved
    assert client.app.state.projects.get.return_value.discussion_text == DISCUSSION


def test_valid_empty_for_nonrequirements(client, monkeypatch):
    mock_http(monkeypatch, lambda r: httpx.Response(200, json=envelope({"quotes": []})))
    use_ollama(client)
    client.app.state.projects.get.return_value.discussion_text = "Hi! We will meet on Friday."
    assert client.post(URL).json()["candidates"] == []


def test_computed_offsets_unicode_crlf_and_repeated_quotes():
    source = "👋\r\nGuests must not delete accounts.\r\nGuests must not delete accounts."
    data = generated(["Guests must not delete accounts."])
    output = resolve_quotes(source, OllamaQuotes.model_validate(data))
    run = build_run(source, output, ID, "mock", "ollama")
    span = run.candidates[0].evidence[0]
    assert span.start == 3  # First exact occurrence, deterministic Unicode offsets.
    assert source[span.start:span.end] == span.quote
    assert run.candidates[0].requirement_text == "Guests must not delete accounts."


def test_old_runs_read_without_provider_and_without_revalidation(client):
    saved = client.post(URL).json()
    doc = client.app.state.extractions.collection.documents[0]
    doc.pop("provider")
    doc["prompt_version"] = "c1-atomic-evidence-v1"
    doc["candidates"][0]["requirement_text"] = "Previously saved paraphrase"
    response = client.get(URL + "/latest")
    assert response.status_code == 200
    assert response.json()["provider"] == "anthropic"
    assert response.json()["run_id"] == saved["run_id"]
    assert response.json()["candidates"][0]["requirement_text"] == "Previously saved paraphrase"


def test_database_write_failure_keeps_latest(client, monkeypatch):
    mock_http(monkeypatch, lambda r: httpx.Response(200, json=envelope()))
    use_ollama(client)
    saved = client.post(URL).json()
    client.app.state.extractions.collection.insert_one = AsyncMock(side_effect=OperationFailure("secret"))
    assert client.post(URL).status_code == 503
    assert client.get(URL + "/latest").json() == saved


def test_explicit_provider_selection_and_health_without_ollama(monkeypatch):
    monkeypatch.setenv("C1_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("C1_OLLAMA_MODEL", "custom-model")
    monkeypatch.setenv("C1_OLLAMA_BASE_URL", "http://127.0.0.1:11435/")
    settings = Settings(_env_file=None, mongodb_uri=None)
    app = create_app(settings)
    assert isinstance(app.state.extraction_provider, OllamaProvider)
    assert app.state.extraction_provider.model_identifier == "custom-model"
    assert settings.ollama_base_url == "http://127.0.0.1:11435"
    with TestClient(app) as c:
        assert c.get("/api/v1/component-1/health").status_code == 200
    assert isinstance(create_app(Settings(_env_file=None, llm_provider="anthropic")).state.extraction_provider, AnthropicProvider)


@pytest.mark.parametrize("setting,value", [
    ("llm_provider", "unknown"), ("ollama_model", " "),
    ("ollama_base_url", "http://user:secret@localhost:11434"),
    ("ollama_base_url", "http://localhost:11434/api/chat"),
    ("ollama_max_tokens", 31), ("ollama_max_tokens", 16385),
    ("ollama_context_length", 0), ("ollama_context_length", 131073),
])
def test_ollama_configuration_validation(setting, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{setting: value})


def test_ollama_whole_operation_deadline(monkeypatch):
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(2)
            yield b'{}'
    mock_http(monkeypatch, lambda r: httpx.Response(200, stream=SlowStream()))
    with pytest.raises(ProviderTimeout):
        asyncio.run(OllamaProvider(Settings(_env_file=None, llm_timeout_seconds=1)).extract(DISCUSSION))


def test_compact_custom_options_and_strict_wire_schema(client, monkeypatch):
    def handler(request):
        payload = json.loads(request.content)
        assert payload["options"] == {"temperature": 0, "num_ctx": 4096, "num_predict": 512}
        return httpx.Response(200, json=envelope({"quotes": EXPECTED, "requirement_text": "fabricated"}))
    mock_http(monkeypatch, handler)
    use_ollama(client)
    client.app.state.extraction_provider = OllamaProvider(Settings(
        _env_file=None, ollama_context_length=4096, ollama_max_tokens=512, llm_max_tokens=16384))
    assert client.post(URL).status_code == 502
    assert client.app.state.extractions.collection.documents == []


def test_whitespace_normalization_from_live_response_is_not_repaired(client, monkeypatch):
    quotes = [EXPECTED[0], "Only administrators can delete accounts.", EXPECTED[2],
              "We will meet on Friday."]
    mock_http(monkeypatch, lambda r: httpx.Response(200, json=envelope(generated(quotes))))
    use_ollama(client)
    assert client.post(URL).status_code == 502
    assert client.app.state.extractions.collection.documents == []
    assert client.app.state.projects.get.return_value.discussion_text == DISCUSSION
