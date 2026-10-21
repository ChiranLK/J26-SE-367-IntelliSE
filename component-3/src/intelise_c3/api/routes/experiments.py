"""Isolated experimental routes for TeamSocLo Claude code-generation workflows."""

from fastapi import APIRouter, Request, status

from intelise_c3.contracts.generation import CodeGenerationRequest, GenerationMode
from intelise_c3.contracts.demo import OpenRouterCheck
from intelise_c3.core.errors import ApplicationError, ErrorDetail, ErrorResponse
from intelise_c3.domain.llm import LLMInferenceRequest, LLMMessage
from intelise_c3.domain.generation import GenerationRunResult
from intelise_c3.llm.openrouter import OpenRouterLLMClient
from intelise_c3.llm.teamsoclo import TeamSocLoClaudeLLMClient
from intelise_c3.rag.runtime import RagRuntime
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.design_context_store import DesignContextStore

router = APIRouter(prefix="/experiments", tags=["experiments"])


def require_teamsoclo_enabled(settings) -> None:
    if not settings.teamsoclo_experiment_enabled:
        raise ApplicationError(
            [
                ErrorDetail(
                    code="EXPERIMENT_DISABLED",
                    field="teamsoclo_experiment_enabled",
                    message=(
                        "TeamSocLo generation is disabled by configuration. "
                        "Set TEAMSOCLO_EXPERIMENT_ENABLED=true in the backend environment to enable."
                    ),
                )
            ],
            status_code=status.HTTP_403_FORBIDDEN,
        )


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
    require_teamsoclo_enabled(settings)

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


def require_openrouter_enabled(settings) -> None:
    if not settings.openrouter_experiment_enabled:
        raise ApplicationError(
            [
                ErrorDetail(
                    code="EXPERIMENT_DISABLED",
                    field="openrouter_experiment_enabled",
                    message=(
                        "The OpenRouter experimental workflow is disabled by configuration. "
                        "Set OPENROUTER_EXPERIMENT_ENABLED=true in the backend environment to enable."
                    ),
                )
            ],
            status_code=status.HTTP_403_FORBIDDEN,
        )


@router.post(
    "/openrouter-generation",
    response_model=GenerationRunResult,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Malformed request or invalid generation mode."},
        403: {"model": ErrorResponse, "description": "OpenRouter experimental workflow is disabled."},
        409: {"model": ErrorResponse, "description": "Generation context, stack, or approval conflict."},
        422: {"model": ErrorResponse, "description": "Malformed request or unsafe generated artifact."},
        429: {"model": ErrorResponse, "description": "OpenRouter rate limit exceeded."},
        502: {"model": ErrorResponse, "description": "OpenRouter authentication, credit or response error."},
        503: {"model": ErrorResponse, "description": "OpenRouter unavailable or API key missing."},
        504: {"model": ErrorResponse, "description": "OpenRouter inference timeout."},
    },
    summary="Explicitly run the isolated experimental OpenRouter code-generation workflow",
)
async def create_openrouter_generation_run(
    generation_request: CodeGenerationRequest,
    request: Request,
) -> GenerationRunResult:
    """Generate isolated artifacts with the configured OpenRouter model.

    Requires OPENROUTER_EXPERIMENT_ENABLED=true. Output goes to experiments/ workspaces,
    records provider "openrouter" plus the model OpenRouter actually used, and never
    falls back to (or alters) the local Ollama runtime.
    """
    settings = request.app.state.settings
    require_openrouter_enabled(settings)
    if generation_request.mode is not GenerationMode.EXPERIMENTAL_OPENROUTER:
        generation_request = generation_request.model_copy(
            update={"mode": GenerationMode.EXPERIMENTAL_OPENROUTER}
        )
    service = CodeGenerationService(
        workspace_root=settings.generated_workspace_root,
        llm_client=OpenRouterLLMClient(settings),
        rag_runtime=RagRuntime.from_settings(settings),
        design_context_store=DesignContextStore.from_settings(settings),
    )
    return await service.generate(generation_request)


@router.post(
    "/openrouter-check",
    response_model=OpenRouterCheck,
    responses={
        403: {"model": ErrorResponse, "description": "OpenRouter experimental workflow is disabled."},
        429: {"model": ErrorResponse, "description": "OpenRouter rate limit exceeded."},
        502: {"model": ErrorResponse, "description": "OpenRouter authentication, credit or response error."},
        503: {"model": ErrorResponse, "description": "OpenRouter unavailable or API key missing."},
        504: {"model": ErrorResponse, "description": "OpenRouter inference timeout."},
    },
    summary="Explicit OpenRouter connectivity check with one fixed tiny prompt (no C1/C2 content)",
)
async def check_openrouter(request: Request) -> OpenRouterCheck:
    settings = request.app.state.settings
    require_openrouter_enabled(settings)
    result = await OpenRouterLLMClient(settings).generate(
        LLMInferenceRequest(
            prompt_template_version="openrouter-connectivity-check-v1",
            messages=(LLMMessage(role="user", content="Reply with exactly the word OK."),),
        )
    )
    meta = result.metadata
    return OpenRouterCheck(
        ok=True,
        configured_model=meta.configured_model_identifier,
        response_model=meta.response_model_identifier,
        upstream_provider=getattr(meta.response, "upstream_provider", None),
        reply=result.output_text[:40],
        latency_ms=meta.client_inference_latency_ms,
        total_tokens=getattr(meta.response, "total_tokens", None),
    )
