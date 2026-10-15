"""Versioned request contract for deterministic FR-C3-02 stack selection."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from intelise_c3.domain.design_context import DesignContext


class SelectionContractModel(BaseModel):
    """Strict immutable base for Component 3 selection inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class FrontendTechnology(StrEnum):
    REACT = "REACT"
    ANGULAR = "ANGULAR"


class BackendTechnology(StrEnum):
    NODE_JS = "NODE_JS"
    SPRING_BOOT = "SPRING_BOOT"


class Technology(StrEnum):
    REACT = "REACT"
    ANGULAR = "ANGULAR"
    NODE_JS = "NODE_JS"
    SPRING_BOOT = "SPRING_BOOT"


class BackendRuntime(StrEnum):
    NODE = "NODE"
    JVM = "JVM"


class ArchitectureStyle(StrEnum):
    RAPID_MVP = "RAPID_MVP"
    REST_SPA = "REST_SPA"
    ENTERPRISE_LAYERED = "ENTERPRISE_LAYERED"


class CriterionEvidence(SelectionContractModel):
    """Caller-supplied evidence reference and explicit uncertainty."""

    reference: Annotated[str, Field(min_length=1)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    uncertainty_notes: str | None = None


class SelectionEvidence(SelectionContractModel):
    requirements: CriterionEvidence
    architecture: CriterionEvidence
    team: CriterionEvidence
    deployment: CriterionEvidence


class TeamProficiency(SelectionContractModel):
    """Evidence-backed proficiency inputs; values are normalized from 0 to 1."""

    react: Annotated[float, Field(ge=0.0, le=1.0)]
    angular: Annotated[float, Field(ge=0.0, le=1.0)]
    node_js: Annotated[float, Field(ge=0.0, le=1.0)]
    spring_boot: Annotated[float, Field(ge=0.0, le=1.0)]


class StackSelectionCriteria(SelectionContractModel):
    """Explicit manual inputs to the versioned deterministic scoring policy."""

    required_frontend: FrontendTechnology | None = None
    required_backend: BackendTechnology | None = None
    preferred_frontend: FrontendTechnology | None = None
    preferred_backend: BackendTechnology | None = None
    prohibited_technologies: tuple[Technology, ...] = ()
    architecture_style: ArchitectureStyle
    team_proficiency: TeamProficiency
    available_backend_runtimes: Annotated[
        tuple[BackendRuntime, ...], Field(min_length=1)
    ]
    supports_static_spa: bool
    preferred_backend_runtime: BackendRuntime | None = None
    evidence: SelectionEvidence


class StackSelectionRequest(SelectionContractModel):
    """Design context plus evidence-bearing selection criteria."""

    design_context: DesignContext
    criteria: StackSelectionCriteria
