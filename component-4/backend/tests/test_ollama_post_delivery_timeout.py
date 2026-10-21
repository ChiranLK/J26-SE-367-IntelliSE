from unittest.mock import patch

import httpx
import pytest

from app.services.ollama_client import OllamaClient, OllamaInferenceException


VALID_RESPONSE = {
    "software_overview": "Verified overview.",
    "architecture_explanation": "Verified architecture.",
    "api_and_data_flow": "Verified data flow.",
    "setup_and_usage": "Verified usage.",
    "limitations_and_scope": "Verified scope.",
}


class _SuccessfulResponse:
    status_code = 200
    text = ""

    def json(self):
        import json

        return {
            "response": json.dumps(VALID_RESPONSE),
            "prompt_eval_count": 708,
            "eval_count": 251,
        }


def test_post_delivery_generation_uses_split_timeout_and_bounded_output():
    captured = {}

    class CapturingClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, json):
            captured["url"] = url
            captured["payload"] = json
            return _SuccessfulResponse()

    client = OllamaClient(timeout_seconds=75.0)
    client.check_availability_sync = lambda: (True, ["qwen2.5-coder:3b"], "available")

    with patch("app.services.ollama_client.httpx.Client", CapturingClient):
        result = client.generate_post_delivery_understanding_sync(
            source_code="def calculate(value): return value * 2",
            filename="solution.py",
            structural_facts={"functions": [{"name": "calculate"}]},
            verified_tests=["test_calculate"],
        )

    assert captured["timeout"].connect == client.connect_timeout_seconds
    assert captured["timeout"].read == 75.0
    assert captured["payload"]["options"]["num_predict"] == client.max_output_tokens == 800
    assert captured["payload"]["keep_alive"] == "10m"
    assert result["_provenance"]["genuine_inference"] is True
    assert result["_provenance"]["fallback_used"] is False


def test_post_delivery_read_timeout_identifies_generation_phase():
    class ReadTimeoutClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, json):
            request = httpx.Request("POST", url)
            raise httpx.ReadTimeout("model still generating", request=request)

    client = OllamaClient(timeout_seconds=12.0)
    client.check_availability_sync = lambda: (True, ["qwen2.5-coder:3b"], "available")

    with patch("app.services.ollama_client.httpx.Client", ReadTimeoutClient):
        with pytest.raises(OllamaInferenceException, match="generation timed out after 12.0s"):
            client.generate_post_delivery_understanding_sync(
                source_code="def verified(): return True",
                filename="solution.py",
                structural_facts={"functions": [{"name": "verified"}]},
                verified_tests=["test_verified"],
            )
