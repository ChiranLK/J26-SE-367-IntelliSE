"""Controlled FR-C3-03/04 generation route using the existing FastAPI app."""

from fastapi import APIRouter, Request, status

from intelise_c3.contracts.generation import CodeGenerationRequest, GenerationMode
from intelise_c3.core.errors import ApplicationError, ErrorDetail, ErrorResponse
from intelise_c3.domain.generation import GenerationRunResult
from intelise_c3.llm.ollama import OllamaLLMClient
from intelise_c3.rag.runtime import RagRuntime
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.design_context_store import DesignContextStore

router = APIRouter(tags=["code-generation"])


@router.post(
    "/generation-runs",
    response_model=GenerationRunResult,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "model": ErrorResponse,
            "description": "Generation context or authorization conflict.",
        },
        422: {
            "model": ErrorResponse,
            "description": "Malformed request or unsafe generated artifact.",
        },
        502: {
            "model": ErrorResponse,
            "description": "Invalid local model response.",
        },
        503: {
            "model": ErrorResponse,
            "description": "Local Ollama or configured model unavailable.",
        },
        504: {
            "model": ErrorResponse,
            "description": "Local Ollama inference timeout.",
        },
    },
    summary="Generate an isolated React and Node.js MVP workspace",
)
async def create_generation_run(
    generation_request: CodeGenerationRequest,
    request: Request,
) -> GenerationRunResult:
    """Generate without running, installing, building, or deploying artifacts."""
    if generation_request.mode is GenerationMode.EXPERIMENTAL_CLAUDE:
        raise ApplicationError(
            [
                ErrorDetail(
                    code="EXPERIMENTAL_MODE_REJECTED",
                    field="mode",
                    message=(
                        "Experimental Claude generation is forbidden on the default "
                        "research endpoint /api/v1/generation-runs. Use the dedicated "
                        "experimental endpoint /api/v1/experiments/claude-generation."
                    ),
                )
            ],
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    settings = request.app.state.settings
    llm_client = (
        OllamaLLMClient(settings)
        if generation_request.mode is GenerationMode.LOCAL_LLM
        else None
    )
    service = CodeGenerationService(
        workspace_root=settings.generated_workspace_root,
        llm_client=llm_client,
        rag_runtime=RagRuntime.from_settings(settings),
        design_context_store=DesignContextStore.from_settings(settings),
    )
    return await service.generate(generation_request)
