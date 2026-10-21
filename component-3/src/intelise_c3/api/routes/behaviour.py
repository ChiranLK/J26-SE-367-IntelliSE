"""Behaviour (non-CRUD) generator routes, Stage 0: generate, then explicitly start on a new port."""

from pathlib import PurePosixPath

from fastapi import APIRouter, Request, Response, status

from intelise_c3.api.routes.experiments import require_openrouter_enabled, require_teamsoclo_enabled
from intelise_c3.contracts.behaviour import BehaviourAppRequest, BehaviourGenerationRequest
from intelise_c3.contracts.generation import GenerationMode
from intelise_c3.core.config import COMPONENT_ROOT
from intelise_c3.core.errors import ApplicationError, ErrorDetail, ErrorResponse
from intelise_c3.domain.behaviour import BehaviourAppSession, BehaviourGenerationResult
from intelise_c3.llm.client import LLMClient
from intelise_c3.llm.ollama import OllamaLLMClient
from intelise_c3.llm.openrouter import OpenRouterLLMClient
from intelise_c3.llm.teamsoclo import TeamSocLoClaudeLLMClient
from intelise_c3.rag.runtime import RagRuntime
from intelise_c3.services import behaviour_export
from intelise_c3.services.behaviour_apps import BehaviourAppRunner
from intelise_c3.services.behaviour_generation import BehaviourGenerationService

router = APIRouter(prefix="/behaviour", tags=["behaviour-generation"])

_ERRORS = {
    400: {"model": ErrorResponse, "description": "Unsupported mode."},
    404: {"model": ErrorResponse, "description": "Workspace not found."},
    409: {"model": ErrorResponse, "description": "Authorization conflict or tampered workspace."},
    422: {"model": ErrorResponse, "description": "Design not renderable or model output rejected."},
    502: {"model": ErrorResponse, "description": "Invalid model response or app start failure."},
    503: {"model": ErrorResponse, "description": "Ollama or Node.js unavailable."},
    504: {"model": ErrorResponse, "description": "Ollama timeout."},
}


def _runner(request: Request) -> BehaviourAppRunner:
    settings = request.app.state.settings
    return BehaviourAppRunner(settings.generated_workspace_root, COMPONENT_ROOT / "runtime" / "behaviour-apps")


@router.post(
    "/generation-runs",
    response_model=BehaviourGenerationResult,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Generate a behaviour (non-CRUD) application with the local model, class by class",
)
async def create_behaviour_run(payload: BehaviourGenerationRequest, request: Request) -> BehaviourGenerationResult:
    settings = request.app.state.settings

    if (
        payload.mode is GenerationMode.LOCAL_LLM
        and getattr(settings, "generation_provider", "ollama") == "openrouter"
    ):
        raise ApplicationError(
            [
                ErrorDetail(
                    code="LOCAL_OLLAMA_DISABLED",
                    field="mode",
                    message=(
                        "Local Ollama is disabled by GENERATION_PROVIDER=openrouter. "
                        "Choose EXPERIMENTAL_OPENROUTER."
                    ),
                )
            ],
            status_code=status.HTTP_409_CONFLICT,
        )

    if payload.mode is GenerationMode.EXPERIMENTAL_CLAUDE:
        require_teamsoclo_enabled(settings)

        def client_for(temperature: float) -> LLMClient:
            return TeamSocLoClaudeLLMClient(settings)

    elif payload.mode is GenerationMode.EXPERIMENTAL_OPENROUTER:
        # Same explicit gate as /experiments/openrouter-generation; never a silent fallback.
        require_openrouter_enabled(settings)

        def client_for(temperature: float) -> LLMClient:
            return OpenRouterLLMClient(settings, temperature=temperature)

    else:

        def client_for(temperature: float) -> LLMClient:
            return OllamaLLMClient(settings.model_copy(update={"ollama_temperature": temperature}))

    configured_model = {
        GenerationMode.LOCAL_LLM: settings.ollama_model,
        GenerationMode.EXPERIMENTAL_CLAUDE: settings.teamsoclo_model,
        GenerationMode.EXPERIMENTAL_OPENROUTER: settings.openrouter_model,
    }.get(payload.mode, "unsupported")
    service = BehaviourGenerationService(
        settings.generated_workspace_root,
        client_for,
        configured_model=configured_model,
        batch_mode=payload.mode is GenerationMode.EXPERIMENTAL_OPENROUTER,
        rag_runtime=RagRuntime.from_settings(settings),
    )
    return await service.generate(payload)


@router.post("/apps/start", response_model=BehaviourAppSession, responses=_ERRORS, summary="Start a generated behaviour app on a free loopback port")
def start_behaviour_app(payload: BehaviourAppRequest, request: Request) -> BehaviourAppSession:
    return _runner(request).start(payload.workspace_relative_path)


@router.post("/apps/stop", response_model=BehaviourAppSession, responses=_ERRORS, summary="Stop a running behaviour app")
def stop_behaviour_app(payload: BehaviourAppRequest, request: Request) -> BehaviourAppSession:
    return _runner(request).stop(payload.workspace_relative_path)


@router.get(
    "/workspace/archive",
    responses={**_ERRORS, 200: {"content": {"application/zip": {}}, "description": "Project zip."}},
    summary="Download the hash-verified generated project as a zip",
)
def download_workspace_archive(workspace_relative_path: str, request: Request) -> Response:
    run_dir, manifest = _runner(request).workspace(workspace_relative_path)
    folder = PurePosixPath(workspace_relative_path).parts[1]
    return Response(
        content=behaviour_export.build_archive(run_dir, manifest, folder),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{folder}-{manifest.generation_run_id[:8]}.zip"'},
    )


@router.get("/apps", response_model=tuple[BehaviourAppSession, ...], summary="List behaviour apps started by this backend")
def list_behaviour_apps(request: Request) -> tuple[BehaviourAppSession, ...]:
    return _runner(request).list()
