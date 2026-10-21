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


class OpenRouterStatus(DomainModel):
    """Configuration state only (no network call); the key itself is never exposed."""

    enabled: bool = False
    key_configured: bool = False
    model: str | None = None


class TeamSocLoStatus(DomainModel):
    """Configuration state only; the API key itself is never exposed."""

    enabled: bool = False
    key_configured: bool = False
    model: str | None = None


class OpenRouterCheck(DomainModel):
    """Result of one explicit, tiny OpenRouter connectivity call (no C1/C2 content)."""

    ok: bool
    configured_model: str
    response_model: str
    upstream_provider: str | None = None
    reply: str
    latency_ms: float
    total_tokens: int | None = None


class DemoOverview(DomainModel):
    service_name: str
    api_version: str
    generation_provider: Literal["ollama", "openrouter"] = "ollama"
    ollama: OllamaStatus
    openrouter: OpenRouterStatus = OpenRouterStatus()
    teamsoclo: TeamSocLoStatus = TeamSocLoStatus()
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


class CrudDomainSummary(DomainModel):
    domain_id: str
    title: str
    fixture_id: str
    classification: Literal["SIMULATED_C1_C2_FIXTURE"] = "SIMULATED_C1_C2_FIXTURE"
    notice: str


class CrudDomainCatalog(DomainModel):
    catalog_version: Literal["1.0"] = "1.0"
    review_status: Literal["NOT_INDEPENDENTLY_REVIEWED"] = "NOT_INDEPENDENTLY_REVIEWED"
    domains: tuple[CrudDomainSummary, ...]


class PreviewRunRequest(DomainModel):
    manifest: GenerationManifest
    workspace_relative_path: Annotated[str, Field(min_length=1, max_length=300)]


class PreviewIdRequest(DomainModel):
    preview_id: Annotated[str, Field(min_length=1, max_length=64)]


class PreviewSessionResponse(DomainModel):
    preview_id: str
    generation_run_id: str
    workspace_relative_path: str
    artifact_digest_sha256: str
    status: str
    image_tag: str | None = None
    container_name: str | None = None
    ui_port: int | None = None
    api_port: int | None = None
    ui_url: str | None = None
    api_url: str | None = None
    last_error: str | None = None
    updated_at_utc: str
    execution_claim: Literal[
        "GENERATED_JS_EXECUTES_ONLY_INSIDE_DISPOSABLE_DOCKER_CONTAINER_NOT_ON_HOST"
    ]
    runtime_db_claim: Literal["IN_MEMORY"] = "IN_MEMORY"
    browser_verification_claim: Literal[False] = False


class DefectiveBaseline(DomainModel):
    """A real generation run whose model output is a deliberately defective test double."""

    classification: Literal["SIMULATED_DEFECTIVE_BASELINE"] = "SIMULATED_DEFECTIVE_BASELINE"
    model_evidence_class: Literal["MOCKED_TEST_DOUBLE"] = "MOCKED_TEST_DOUBLE"
    notice: str
    injected_defect_module: str
    generation_run: GenerationRunResult
    design_context: DesignContext
    graph_snapshot: TraceGraphSnapshot
