"""Manual fixed-prompt smoke test for the configured local Ollama model."""

import asyncio

from intelise_c3.core.config import get_settings
from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.llm import LLMInferenceRequest, LLMMessage
from intelise_c3.llm.ollama import OllamaLLMClient

SMOKE_TEMPLATE_VERSION = "c3-local-ollama-smoke-v1"


async def run_smoke_test() -> int:
    """Run one harmless fixed prompt and print non-sensitive diagnostics."""
    settings = get_settings()
    request = LLMInferenceRequest(
        prompt_template_version=SMOKE_TEMPLATE_VERSION,
        messages=(
            LLMMessage(
                role="system",
                content=(
                    "You are a local connectivity test. Do not call tools and do "
                    "not generate or execute software."
                ),
            ),
            LLMMessage(role="user", content="Reply with LOCAL_OLLAMA_OK."),
        ),
    )
    try:
        result = await OllamaLLMClient(settings).generate(request)
    except ApplicationError as exception:
        error = exception.errors[0]
        print(f"Smoke test failed [{error.code}]: {error.message}")
        return 1

    print("Local Ollama smoke test succeeded.")
    print(f"Configured model: {result.metadata.configured_model_identifier}")
    print(f"Response model: {result.metadata.response_model_identifier}")
    print(f"Prompt template: {result.metadata.prompt_template_version}")
    print(f"Client latency: {result.metadata.client_inference_latency_ms} ms")
    print(f"Response: {result.output_text}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run_smoke_test()))


if __name__ == "__main__":
    main()
