"""Component 3 request contract for controlled MVP code generation."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from intelise_c3.domain.design_context import DesignContext
from intelise_c3.domain.generation_context import GenerationContext
from intelise_c3.domain.stack_selection import StackSelectionReport


class GenerationContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GenerationMode(StrEnum):
    LOCAL_LLM = "LOCAL_LLM"
    TEMPLATE_ONLY = "TEMPLATE_ONLY"
    EXPERIMENTAL_CLAUDE = "EXPERIMENTAL_CLAUDE"
    EXPERIMENTAL_OPENROUTER = "EXPERIMENTAL_OPENROUTER"


class ProvisionalApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED_FOR_MVP_GENERATION = "APPROVED_FOR_MVP_GENERATION"
    REJECTED = "REJECTED"


class ProvisionalStackApproval(GenerationContractModel):
    """Caller assertion requiring authoritative verification in real integration."""

    status: ProvisionalApprovalStatus
    approval_reference: Annotated[str, Field(min_length=1)]
    approved_by: Annotated[str, Field(min_length=1)]
    acknowledges_provisional_policy: bool


class CodeGenerationRequest(GenerationContractModel):
    """Validated contexts plus an explicit, provisional generation decision."""

    generation_context: GenerationContext
    design_context: DesignContext
    stack_selection_report: StackSelectionReport
    stack_approval: ProvisionalStackApproval
    mode: GenerationMode
    workspace_name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=64,
            pattern=r"^[a-z0-9][a-z0-9._-]*$",
        ),
    ] = "task-management-mvp"
