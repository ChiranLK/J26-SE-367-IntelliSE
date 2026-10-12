"""Provider-neutral interface for Component 3 inference clients."""

from typing import Protocol, runtime_checkable

from intelise_c3.domain.llm import LLMInferenceRequest, LLMInferenceResponse


@runtime_checkable
class LLMClient(Protocol):
    """Interface reusable by future generation and regeneration agents."""

    async def generate(self, request: LLMInferenceRequest) -> LLMInferenceResponse:
        """Generate one validated response without executing its content."""
        ...
