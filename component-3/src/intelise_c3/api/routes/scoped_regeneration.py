"""Versioned routes for defect-scoped impact selection and regeneration."""

from fastapi import APIRouter, Request

from intelise_c3.contracts.scoped_regeneration import ScopedRegenerationRequest
from intelise_c3.core.errors import ErrorResponse
from intelise_c3.domain.scoped_regeneration import (
    ImpactSelectionReport,
    ScopedRegenerationResult,
)
from intelise_c3.llm.ollama import OllamaLLMClient
from intelise_c3.rag.defect_context import ChromaDefectContextStore
from intelise_c3.rag.runtime import RagRuntime
from intelise_c3.services.scoped_regeneration import ScopedRegenerationService
from intelise_c3.services.traceability import TraceabilityService
from intelise_c3.traceability.builder import TraceabilityGraphBuilder
from intelise_c3.traceability.store import SQLiteTraceabilityStore
from intelise_c3.traceability.verification import ManifestVerificationService

router = APIRouter(tags=["scoped-regeneration"])

_ERRORS = {
    404: {"model": ErrorResponse, "description": "No graph exists for the source run."},
    409: {
        "model": ErrorResponse,
        "description": "Stale, mismatched, or unverified defect report, run, or graph.",
    },
    422: {"model": ErrorResponse, "description": "Malformed defect report or unsafe path."},
    503: {"model": ErrorResponse, "description": "Local Ollama unavailable."},
}


def _service(request: Request, *, with_model: bool) -> ScopedRegenerationService:
    settings = request.app.state.settings
    traceability = TraceabilityService(
        verifier=ManifestVerificationService(settings.generated_workspace_root),
        builder=TraceabilityGraphBuilder(),
        store=SQLiteTraceabilityStore(settings.traceability_store_path),
    )
    service_args = {}
    if with_model:
        configured_rag_model = getattr(settings, "rag_embedding_model", None)
        defect_store = getattr(
            request.app.state, "trigger_c_defect_context_store", None
        )
        rag_runtime = getattr(request.app.state, "trigger_c_rag_runtime", None)
        if defect_store is None:
            defect_store = ChromaDefectContextStore(
                settings.rag_persist_dir,
                configured_rag_model,
            )
        if rag_runtime is None:
            rag_runtime = RagRuntime.from_settings(settings)
        service_args = {
            "defect_context_store": defect_store,
            "rag_runtime": rag_runtime,
            "rag_a_backend": getattr(
                request.app.state, "trigger_c_rag_a_backend", "chroma"
            ),
            "rag_a_embedding_model": getattr(
                request.app.state,
                "trigger_c_rag_a_embedding_model",
                configured_rag_model,
            ),
        }
    return ScopedRegenerationService(
        settings.generated_workspace_root,
        traceability,
        OllamaLLMClient(settings) if with_model else None,
        model_evidence_class=getattr(
            request.app.state,
            "trigger_c_model_evidence_class",
            "REAL_LOCAL_OLLAMA",
        ),
        **service_args,
    )


@router.post(
    "/impact-selections",
    response_model=ImpactSelectionReport,
    responses=_ERRORS,
    summary="Select a justified patch scope from a simulated C4 defect report",
)
def select_impact(
    payload: ScopedRegenerationRequest,
    request: Request,
) -> ImpactSelectionReport:
    """Read-only: no model call and no workspace or graph change."""
    return _service(request, with_model=False).select_impact(payload)


@router.post(
    "/scoped-regenerations",
    response_model=ScopedRegenerationResult,
    responses=_ERRORS,
    summary="Patch only graph-selected modules and hand a PENDING re-test to C4",
)
async def create_scoped_regeneration(
    payload: ScopedRegenerationRequest,
    request: Request,
) -> ScopedRegenerationResult:
    """Never overwrites the source run and never claims a repair succeeded."""
    return await _service(request, with_model=True).regenerate(payload)
