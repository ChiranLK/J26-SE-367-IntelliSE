"""Opt-in integration test for a real local Ollama installation."""

import asyncio
import os

import pytest

from intelise_c3.core.config import Settings
from intelise_c3.domain.llm import LLMInferenceRequest, LLMMessage
from intelise_c3.llm.ollama import OllamaLLMClient


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_INTEGRATION") != "1",
    reason="Set RUN_OLLAMA_INTEGRATION=1 to call the real local Ollama service.",
)
def test_real_local_ollama_smoke_response() -> None:
    settings = Settings()
    request = LLMInferenceRequest(
        prompt_template_version="c3-pytest-local-ollama-smoke-v1",
        messages=(
            LLMMessage(
                role="system",
                content="This is a local connectivity test. Do not call tools.",
            ),
            LLMMessage(role="user", content="Reply with LOCAL_OLLAMA_OK."),
        ),
    )

    result = asyncio.run(OllamaLLMClient(settings).generate(request))

    assert result.output_text.strip()
    assert result.metadata.provider == "ollama-local"
    assert result.metadata.configured_model_identifier == settings.ollama_model
    assert result.metadata.response.done is True
