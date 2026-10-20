"""Isolated experimental routes for TeamSocLo Claude code-generation workflows."""

from fastapi import APIRouter, Request, status

from intelise_c3.contracts.generation import CodeGenerationRequest, GenerationMode
from intelise_c3.core.errors import ApplicationError, ErrorDetail, ErrorResponse
from intelise_c3.domain.generation import GenerationRunResult
from intelise_c3.llm.teamsoclo import TeamSocLoClaudeLLMClient
from intelise_c3.rag.runtime import RagRuntime
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.design_context_store import DesignContextStore

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post(
    "/claude-generation",
    response_model=GenerationRunResult,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Malformed request or invalid generation mode.",
        },
        403: {
            "model": ErrorResponse,
            "description": "TeamSocLo Claude experimental workflow is disabled.",
        },
        409: {
            "model": ErrorResponse,
            "description": "Generation context, stack, or approval conflict.",
        },
        422: {
            "model": ErrorResponse,
            "description": "Malformed request or unsafe generated artifact.",
        },
        502: {
            "model": ErrorResponse,
            "description": "TeamSocLo gateway authentication or response error.",
        },
        503: {
            "model": ErrorResponse,
            "description": "TeamSocLo gateway unavailable or API key missing.",
        },
        504: {
            "model": ErrorResponse,
            "description": "TeamSocLo gateway inference timeout.",
        },
    },
    summary="Explicitly run isolated experimental Claude code-generation workflow",
)
async def create_claude_generation_run(
    generation_request: CodeGenerationRequest,
    request: Request,
) -> GenerationRunResult:
    """Generate isolated artifacts using TeamSocLo Claude Haiku 4.5.

    This endpoint requires TEAMSOCLO_EXPERIMENT_ENABLED=true in the backend settings.
    It writes generated artifacts to isolated experimental workspace paths and never
    alters or falls back to the default local Ollama runtime.
    """
    settings = request.app.state.settings
    if not settings.teamsoclo_experiment_enabled:
        raise ApplicationError(
            [
                ErrorDetail(
                    code="EXPERIMENT_DISABLED",
                    field="teamsoclo_experiment_enabled",
                    message=(
                        "TeamSocLo Claude experimental workflow is disabled by configuration. "
                        "Set TEAMSOCLO_EXPERIMENT_ENABLED=true in backend environment to enable."
                    ),
                )
            ],
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Force experimental mode for this endpoint if not already set
    if generation_request.mode is not GenerationMode.EXPERIMENTAL_CLAUDE:
        generation_request = generation_request.model_copy(
            update={"mode": GenerationMode.EXPERIMENTAL_CLAUDE}
        )

    claude_client = TeamSocLoClaudeLLMClient(settings)
    service = CodeGenerationService(
        workspace_root=settings.generated_workspace_root,
        llm_client=claude_client,
        rag_runtime=RagRuntime.from_settings(settings),
        design_context_store=DesignContextStore.from_settings(settings),
    )
    return await service.generate(generation_request)
