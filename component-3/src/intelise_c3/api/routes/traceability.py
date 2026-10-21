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
    ImpactSet,
    RequirementTraceChain,
    RtmExport,
    TraceGraphSnapshot,
    TraceabilityEvaluationReport,
    TraceabilityMetricsReport,
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


@router.get(
    "/graphs/{graph_id}/chains/{requirement_id}",
    response_model=RequirementTraceChain,
    responses=_ERRORS,
    summary="Get the end-to-end trace chain for a requirement from the latest graph",
)
def get_latest_chain(
    graph_id: str,
    requirement_id: str,
    request: Request,
) -> RequirementTraceChain:
    return _service(request).chain(graph_id, requirement_id)


@router.get(
    "/graphs/{graph_id}/versions/{version}/chains/{requirement_id}",
    response_model=RequirementTraceChain,
    responses=_ERRORS,
    summary="Get the end-to-end trace chain for a requirement from a specific graph version",
)
def get_versioned_chain(
    graph_id: str,
    version: int,
    requirement_id: str,
    request: Request,
) -> RequirementTraceChain:
    return _service(request).chain(graph_id, requirement_id, version=version)


@router.get(
    "/graphs/{graph_id}/impact/{requirement_id}",
    response_model=ImpactSet,
    responses=_ERRORS,
    summary="Get the impacted downstream nodes and files for a requirement from the latest graph",
)
def get_latest_impact_set(
    graph_id: str,
    requirement_id: str,
    request: Request,
) -> ImpactSet:
    return _service(request).impact_set(graph_id, requirement_id)


@router.get(
    "/graphs/{graph_id}/versions/{version}/impact/{requirement_id}",
    response_model=ImpactSet,
    responses=_ERRORS,
    summary="Get the impacted downstream nodes and files for a requirement from a specific graph version",
)
def get_versioned_impact_set(
    graph_id: str,
    version: int,
    requirement_id: str,
    request: Request,
) -> ImpactSet:
    return _service(request).impact_set(graph_id, requirement_id, version=version)


@router.get(
    "/graphs/{graph_id}/modules/{module_identifier}/requirements",
    response_model=tuple[str, ...],
    responses=_ERRORS,
    summary="Reverse lookup of requirement IDs for a code module from the latest graph",
)
def get_latest_module_requirements(
    graph_id: str,
    module_identifier: str,
    request: Request,
) -> tuple[str, ...]:
    return _service(request).requirements_for_module(graph_id, module_identifier)


@router.get(
    "/graphs/{graph_id}/versions/{version}/modules/{module_identifier}/requirements",
    response_model=tuple[str, ...],
    responses=_ERRORS,
    summary="Reverse lookup of requirement IDs for a code module from a specific graph version",
)
def get_versioned_module_requirements(
    graph_id: str,
    version: int,
    module_identifier: str,
    request: Request,
) -> tuple[str, ...]:
    return _service(request).requirements_for_module(graph_id, module_identifier, version=version)


@router.get(
    "/graphs/{graph_id}/rtm",
    response_model=RtmExport,
    responses=_ERRORS,
    summary="Export the Requirements Traceability Matrix as JSON and table from the latest graph",
)
def get_latest_rtm(
    graph_id: str,
    request: Request,
) -> RtmExport:
    return _service(request).export_rtm(graph_id)


@router.get(
    "/graphs/{graph_id}/versions/{version}/rtm",
    response_model=RtmExport,
    responses=_ERRORS,
    summary="Export the Requirements Traceability Matrix as JSON and table from a specific graph version",
)
def get_versioned_rtm(
    graph_id: str,
    version: int,
    request: Request,
) -> RtmExport:
    return _service(request).export_rtm(graph_id, version=version)


@router.get(
    "/graphs/{graph_id}/metrics",
    response_model=TraceabilityMetricsReport,
    responses=_ERRORS,
    summary="Retrieve the living traceability metrics report for the latest graph",
)
def get_latest_metrics(
    graph_id: str,
    request: Request,
) -> TraceabilityMetricsReport:
    return _service(request).metrics(graph_id)


@router.get(
    "/graphs/{graph_id}/versions/{version}/metrics",
    response_model=TraceabilityMetricsReport,
    responses=_ERRORS,
    summary="Retrieve the living traceability metrics report for a specific graph version",
)
def get_versioned_metrics(
    graph_id: str,
    version: int,
    request: Request,
) -> TraceabilityMetricsReport:
    return _service(request).metrics(graph_id, version=version)
