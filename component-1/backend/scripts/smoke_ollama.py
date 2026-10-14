"""Single live generation using the real adapter, synthetic data and no database.

Prints the actual response and elapsed time. Never retries or downloads a model.
Uses explicit settings rather than reading a potentially credential-bearing .env.
"""
import asyncio
import json
from time import perf_counter

import httpx

from intelise_c1.core.config import Settings
from intelise_c1.services.extraction import InvalidExtraction, build_run
from intelise_c1.services.provider import OllamaProvider, ProviderTimeout, ProviderUnavailable

SOURCE = ("Customers can book appointments. Only administrators can delete\n"
          "accounts. Search results must appear within two seconds.\nWe will meet on Friday.")
EXPECTED = ["Customers can book appointments.", "Only administrators can delete\naccounts.",
            "Search results must appear within two seconds."]


async def main():
    settings = Settings(_env_file=None, llm_provider="ollama")
    provider = OllamaProvider(settings)
    actual = None
    request_metrics = {}
    real_client = httpx.AsyncClient

    async def capture_request(request):
        payload = json.loads(request.content)
        request_metrics.update(options=payload["options"],
                               schema_bytes=len(json.dumps(payload["format"]).encode()),
                               system_prompt_characters=len(payload["messages"][0]["content"]),
                               timeout_seconds=settings.llm_timeout_seconds)

    async def capture(response):
        nonlocal actual
        # Synthetic discussion only. Capture the bounded wire response for audit.
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > settings.llm_response_max_bytes:
                raise InvalidExtraction("Response exceeded configured byte limit.")
        response._content = bytes(body)
        if response.status_code == 200:
            try:
                actual = json.loads(body)
            except ValueError:
                actual = {"invalid_json": body.decode("utf-8", errors="replace")}

    httpx.AsyncClient = lambda **kwargs: real_client(event_hooks={"request": [capture_request], "response": [capture]}, **kwargs)
    start = perf_counter()
    result = {"provider": "ollama", "model": provider.model_identifier,
              "prompt_version": provider.prompt_version, "synthetic_source": SOURCE,
              "source_validation": "not_completed"}
    try:
        output = await provider.extract(SOURCE)
        run = build_run(SOURCE, output, "smoke-only-no-persistence", provider.model_identifier, "ollama", provider.prompt_version)
        texts = [candidate.requirement_text for candidate in run.candidates]
        result.update(validated_candidates=run.model_dump(mode="json")["candidates"],
                      source_validation="passed",
                      fixture_relevance_completeness_match=texts == EXPECTED, status="passed" if texts == EXPECTED else "quality_mismatch")
    except (ProviderTimeout, ProviderUnavailable, InvalidExtraction) as error:
        result.update(source_validation="failed" if isinstance(error, InvalidExtraction) else "not_completed",
                      status=type(error).__name__, error=str(error) or ("Generation timed out; no retry attempted." if isinstance(error, ProviderTimeout) else type(error).__name__))
    finally:
        httpx.AsyncClient = real_client
    # Fixture evaluation is separate from schema/evidence acceptance, including failures.
    if actual is not None:
        try:
            quotes = json.loads(actual["message"]["content"])["quotes"]
            result["fixture_relevance_completeness_match"] = quotes == EXPECTED
        except (KeyError, TypeError, ValueError):
            result["fixture_relevance_completeness_match"] = None
    result.update(elapsed_seconds=round(perf_counter() - start, 3), actual_response=actual, request_metrics=request_metrics)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
