"""Request contracts for the behaviour (non-CRUD) generator, Stage 0."""

from typing import Annotated

from pydantic import Field

from intelise_c3.contracts.generation import CodeGenerationRequest, GenerationContractModel


class BehaviourGenerationRequest(CodeGenerationRequest):
    """The same authorized generation request, plus behaviour-generator options.

    ``mode`` selects the engine: LOCAL_LLM (local Qwen through Ollama) or
    EXPERIMENTAL_CLAUDE (the explicitly gated TeamSocLo API).
    """

    facade_class: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    max_attempts_per_class: Annotated[int, Field(ge=1, le=3)] = 3


class BehaviourAppRequest(GenerationContractModel):
    workspace_relative_path: Annotated[str, Field(min_length=1, max_length=300)]
