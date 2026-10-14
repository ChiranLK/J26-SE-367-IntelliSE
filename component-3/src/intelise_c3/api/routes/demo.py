"""Thin helper routes for the InteliSE C3 research demo dashboard.

The dashboard calls the real Component 3 services directly. These helpers only add
what the services do not already expose: local-service status, clearly labeled
simulated fixtures, a verified display-only code preview, and a MOCK-model entry
point for the scoped-regeneration service (the real Ollama entry point already
exists at ``/scoped-regenerations``). Nothing here executes generated code.
"""

from fastapi import APIRouter, Request

from intelise_c3.contracts.demo import (
    CodePreviewRequest,
    CodePreviewResponse,
    DefectiveBaseline,
    DemoOverview,
    SimulatedFixture,
    WorkspaceRunRequest,
)
from intelise_c3.domain.generation import GenerationRunResult
from intelise_c3.contracts.scoped_regeneration import ScopedRegenerationRequest
from intelise_c3.core.errors import ErrorResponse
from intelise_c3.domain.scoped_regeneration import ScopedRegenerationResult
from intelise_c3.services import demo_support
from intelise_c3.services.scoped_regeneration import ScopedRegenerationService
from intelise_c3.services.traceability import TraceabilityService
from intelise_c3.traceability.builder import TraceabilityGraphBuilder
from intelise_c3.traceability.store import SQLiteTraceabilityStore
from intelise_c3.traceability.verification import ManifestVerificationService

router = APIRouter(prefix="/demo", tags=["research-demo"])

_ERRORS = {
    404: {"model": ErrorResponse, "description": "Unknown fixture, graph, or file."},
    409: {"model": ErrorResponse, "description": "Integrity, version, or gate conflict."},
    422: {"model": ErrorResponse, "description": "Malformed or unsafe input."},
}


@router.get(
    "/overview",
    response_model=DemoOverview,
    summary="Report real local-service status and integration state",
)
def get_overview(request: Request) -> DemoOverview:
    return demo_support.build_overview(request.app.state.settings)


@router.get(
    "/fixtures/{fixture_id}",
    response_model=SimulatedFixture,
    responses=_ERRORS,
    summary="Return one clearly labeled SIMULATED fixture",
)
def get_fixture(fixture_id: str) -> SimulatedFixture:
    return demo_support.load_fixture(fixture_id)


@router.post(
    "/code-preview",
    response_model=CodePreviewResponse,
    responses=_ERRORS,
    summary="Display one verified generated file as text; never executes it",
)
def preview_code(payload: CodePreviewRequest, request: Request) -> CodePreviewResponse:
    verifier = ManifestVerificationService(request.app.state.settings.generated_workspace_root)
    return demo_support.preview_file(verifier, payload)


@router.post(
    "/workspace-run",
    response_model=GenerationRunResult,
    responses=_ERRORS,
    summary="Read and verify the stored manifest of an existing generated workspace",
)
def read_workspace_run(payload: WorkspaceRunRequest, request: Request) -> GenerationRunResult:
    return demo_support.load_workspace_run(request.app.state.settings, payload)


@router.post(
    "/scoped-regeneration/baseline",
    response_model=DefectiveBaseline,
    status_code=201,
    responses=_ERRORS,
    summary="Create a SIMULATED defective baseline run and graph for the repair demo",
)
async def create_baseline(request: Request) -> DefectiveBaseline:
    return await demo_support.create_defective_baseline(request.app.state.settings)


@router.post(
    "/scoped-regenerations/mock",
    response_model=ScopedRegenerationResult,
    responses=_ERRORS,
    summary="Run the real scoped-regeneration service with a deterministic MOCK model",
)
async def create_mock_scoped_regeneration(
    payload: ScopedRegenerationRequest,
    request: Request,
) -> ScopedRegenerationResult:
    """Same pipeline as ``/scoped-regenerations``; only the model output is a test double."""
    settings = request.app.state.settings
    traceability = TraceabilityService(
        verifier=ManifestVerificationService(settings.generated_workspace_root),
        builder=TraceabilityGraphBuilder(),
        store=SQLiteTraceabilityStore(settings.traceability_store_path),
    )
    service = ScopedRegenerationService(
        settings.generated_workspace_root,
        traceability,
        demo_support.mock_repair_client(),
        model_evidence_class="MOCKED_TEST_DOUBLE",
    )
    return await service.regenerate(payload)
