"""Versioned API routes for living requirement traceability."""

from fastapi import APIRouter, Request, status

from intelise_c3.contracts.traceability import (
    GraphComparisonRequest,
    GraphCreateRequest,
    GraphEvaluationRequest,
    GraphUpdateRequest,
)
from intelise_c3.core.errors import ErrorResponse
from intelise_c3.domain.traceability import (
    GraphChangeReport,
    GraphUpdateResult,
    TraceGraphSnapshot,
    TraceabilityEvaluationReport,
)
from intelise_c3.services.traceability import TraceabilityService
from intelise_c3.traceability.builder import TraceabilityGraphBuilder
from intelise_c3.traceability.store import SQLiteTraceabilityStore
from intelise_c3.traceability.verification import ManifestVerificationService

router = APIRouter(prefix="/traceability", tags=["living-traceability"])

_ERRORS = {
    404: {"model": ErrorResponse, "description": "Graph snapshot not found."},
    409: {"model": ErrorResponse, "description": "Integrity or version conflict."},
    422: {"model": ErrorResponse, "description": "Malformed or unsafe input."},
    500: {"model": ErrorResponse, "description": "Local persistence failure."},
}


def _service(request: Request) -> TraceabilityService:
    settings = request.app.state.settings
    return TraceabilityService(
        verifier=ManifestVerificationService(settings.generated_workspace_root),
        builder=TraceabilityGraphBuilder(),
        store=SQLiteTraceabilityStore(settings.traceability_store_path),
    )


@router.post(
    "/graphs",
    response_model=TraceGraphSnapshot,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Create and persist a verified traceability graph snapshot",
)
def create_graph(payload: GraphCreateRequest, request: Request) -> TraceGraphSnapshot:
    return _service(request).create(payload)


@router.get(
    "/graphs/{graph_id}",
    response_model=TraceGraphSnapshot,
    responses=_ERRORS,
    summary="Retrieve the latest graph snapshot",
)
def get_latest_graph(graph_id: str, request: Request) -> TraceGraphSnapshot:
    return _service(request).latest(graph_id)


@router.get(
    "/graphs/{graph_id}/versions/{version}",
    response_model=TraceGraphSnapshot,
    responses=_ERRORS,
    summary="Retrieve one immutable graph version",
)
def get_graph_version(
    graph_id: str,
    version: int,
    request: Request,
) -> TraceGraphSnapshot:
    return _service(request).retrieve(graph_id, version)


@router.post(
    "/graphs/{graph_id}/compare",
    response_model=GraphChangeReport,
    responses=_ERRORS,
    summary="Compare a graph snapshot with a newly verified manifest",
)
def compare_graph(
    graph_id: str,
    payload: GraphComparisonRequest,
    request: Request,
) -> GraphChangeReport:
    return _service(request).compare(graph_id, payload)


@router.post(
    "/graphs/{graph_id}/updates",
    response_model=GraphUpdateResult,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Append a living graph update without overwriting history",
)
def update_graph(
    graph_id: str,
    payload: GraphUpdateRequest,
    request: Request,
) -> GraphUpdateResult:
    return _service(request).update(graph_id, payload)


@router.post(
    "/graphs/{graph_id}/versions/{version}/evaluate",
    response_model=TraceabilityEvaluationReport,
    responses=_ERRORS,
    summary="Evaluate graph links against researcher-curated ground truth",
)
def evaluate_graph(
    graph_id: str,
    version: int,
    payload: GraphEvaluationRequest,
    request: Request,
) -> TraceabilityEvaluationReport:
    return _service(request).evaluate(graph_id, version, payload.ground_truth)
