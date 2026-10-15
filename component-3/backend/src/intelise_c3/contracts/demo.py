"""Contracts for the thin helper API behind the C3 research demo dashboard.

These helpers only expose evidence that already exists in Component 3 (simulated
fixtures, local-service status, verified generated files). They never fabricate
upstream, Component 4, or deployment results.
"""

from typing import Annotated, Any, Literal

from pydantic import Field

from intelise_c3.domain.design_context import DesignContext
from intelise_c3.domain.generation import (
    ArtifactOrigin,
    GeneratedArtifactType,
    GenerationManifest,
    GenerationRunResult,
)
from intelise_c3.domain.generation_context import DomainModel
from intelise_c3.domain.traceability import TraceGraphSnapshot


class OllamaStatus(DomainModel):
    """Result of one real, short, read-only probe of the local Ollama service."""

    base_url: str
    configured_model: str
    reachable: bool
    model_installed: bool | None
    detail: str
    checked_at_utc: str


IntegrationState = Literal[
    "SIMULATED_FIXTURE",
    "NOT_INTEGRATED",
    "NOT_IMPLEMENTED",
    "LOCAL_REAL",
]


class IntegrationStatus(DomainModel):
    component: str
    state: IntegrationState
    note: str


class DemoOverview(DomainModel):
    service_name: str
    api_version: str
    ollama: OllamaStatus
    generated_workspace_root_name: str
    traceability_store_name: str
    integrations: tuple[IntegrationStatus, ...]


class SimulatedFixture(DomainModel):
    """A fixture payload together with an explicit, non-removable provenance label."""

    fixture_id: str
    classification: Literal["SIMULATED_C1_C2_FIXTURE", "SIMULATED_C4_FIXTURE", "SIMULATED_CRITERIA"]
    review_status: Literal["NOT_INDEPENDENTLY_REVIEWED"] = "NOT_INDEPENDENTLY_REVIEWED"
    notice: str
    payload: dict[str, Any]


class CodePreviewRequest(DomainModel):
    manifest: GenerationManifest
    workspace_relative_path: Annotated[str, Field(min_length=1, max_length=300)]
    relative_path: Annotated[str, Field(min_length=1, max_length=300)]


class WorkspaceRunRequest(DomainModel):
    """Identifies an existing generated workspace whose stored manifest should be read."""

    workspace_relative_path: Annotated[str, Field(min_length=1, max_length=300)]


class CodePreviewResponse(DomainModel):
    relative_path: str
    artifact_type: GeneratedArtifactType
    origin: ArtifactOrigin
    sha256: str
    size_bytes: int
    truncated: bool
    content: str
    execution_claim: Literal["DISPLAY_ONLY_NOT_EXECUTED"] = "DISPLAY_ONLY_NOT_EXECUTED"


class DefectiveBaseline(DomainModel):
    """A real generation run whose model output is a deliberately defective test double."""

    classification: Literal["SIMULATED_DEFECTIVE_BASELINE"] = "SIMULATED_DEFECTIVE_BASELINE"
    model_evidence_class: Literal["MOCKED_TEST_DOUBLE"] = "MOCKED_TEST_DOUBLE"
    notice: str
    injected_defect_module: str
    generation_run: GenerationRunResult
    design_context: DesignContext
    graph_snapshot: TraceGraphSnapshot
