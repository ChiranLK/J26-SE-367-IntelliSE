"""Read-only evidence helpers for the C3 research demo dashboard.

Everything here either reports real local state (Ollama probe, verified files) or
serves clearly labeled SIMULATED fixtures. The one write-capable helper creates a
SIMULATED defective baseline through the real generation service so that the
defect-feedback demo has a verified run and graph to act on.
"""

from datetime import UTC, datetime
import json
from pathlib import PurePosixPath

from fastapi import status
import httpx

from intelise_c3.contracts.demo import (
    CodePreviewRequest,
    CodePreviewResponse,
    DefectiveBaseline,
    DemoOverview,
    IntegrationStatus,
    OllamaStatus,
    SimulatedFixture,
    WorkspaceRunRequest,
)
from intelise_c3.contracts.generation import GenerationMode
from intelise_c3.contracts.traceability import GraphCreateRequest
from intelise_c3.core.config import Settings
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.generation import GenerationManifest, GenerationRunResult
from intelise_c3.scripts.generate_task_mvp import (
    SIMULATED_INPUT,
    build_simulated_request,
    build_simulated_stack_criteria,
)
from intelise_c3.scripts.scoped_regeneration_experiment import (
    FIXTURE_DIRECTORY,
    SERVICE_PATH,
    SimulatedModelClient,
    model_output,
)
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.traceability import TraceabilityService
from intelise_c3.traceability.builder import TraceabilityGraphBuilder
from intelise_c3.traceability.store import SQLiteTraceabilityStore
from intelise_c3.traceability.verification import ManifestVerificationService

MAX_PREVIEW_BYTES = 120_000
OLLAMA_PROBE_TIMEOUT_SECONDS = 2.0
DEMO_BASELINE_WORKSPACE_NAME = "demo-defective-baseline"

FIXTURE_IDS = ("input-package", "defect-scenarios", "stack-criteria")

_INTEGRATIONS = (
    IntegrationStatus(
        component="Component 1 (requirements)",
        state="SIMULATED_FIXTURE",
        note="C1 is not integrated. Requirements come from a simulated fixture.",
    ),
    IntegrationStatus(
        component="Component 2 (UML and UI design)",
        state="SIMULATED_FIXTURE",
        note="C2 is not integrated. UML, anchors, and UI artifacts come from a simulated fixture.",
    ),
    IntegrationStatus(
        component="Component 4 (testing, XAI)",
        state="NOT_INTEGRATED",
        note=(
            "No independent testing, XAI, or semantic-preservation results exist. "
            "Defect reports are simulated and retests stay PENDING."
        ),
    ),
    IntegrationStatus(
        component="Deployment",
        state="NOT_IMPLEMENTED",
        note="Component 3 does not deploy generated applications.",
    ),
    IntegrationStatus(
        component="Component 3 services",
        state="LOCAL_REAL",
        note="Validation, design, stack selection, generation, traceability, and regeneration run for real.",
    ),
)


def probe_ollama(settings: Settings) -> OllamaStatus:
    """Make one real read-only call to the local Ollama tag list."""
    base_url = str(settings.ollama_base_url).rstrip("/")
    checked_at = datetime.now(UTC).isoformat()
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=OLLAMA_PROBE_TIMEOUT_SECONDS)
        response.raise_for_status()
        names = {
            str(item.get(key))
            for item in response.json().get("models", [])
            if isinstance(item, dict)
            for key in ("name", "model")
            if item.get(key)
        }
    except (httpx.HTTPError, ValueError) as exception:
        return OllamaStatus(
            base_url=base_url,
            configured_model=settings.ollama_model,
            reachable=False,
            model_installed=None,
            detail=f"Ollama probe failed ({type(exception).__name__}).",
            checked_at_utc=checked_at,
        )
    installed = settings.ollama_model in names
    return OllamaStatus(
        base_url=base_url,
        configured_model=settings.ollama_model,
        reachable=True,
        model_installed=installed,
        detail=(
            "Ollama is reachable and the configured model is installed."
            if installed
            else "Ollama is reachable but the configured model is not installed."
        ),
        checked_at_utc=checked_at,
    )


def build_overview(settings: Settings) -> DemoOverview:
    return DemoOverview(
        service_name=settings.service_name,
        api_version=settings.api_version,
        ollama=probe_ollama(settings),
        generated_workspace_root_name=settings.generated_workspace_root.name,
        traceability_store_name=settings.traceability_store_path.name,
        integrations=_INTEGRATIONS,
    )


def load_fixture(fixture_id: str) -> SimulatedFixture:
    if fixture_id == "input-package":
        return SimulatedFixture(
            fixture_id=fixture_id,
            classification="SIMULATED_C1_C2_FIXTURE",
            notice=(
                "SIMULATED C1/C2 package authored for the Task Management MVP. It is not "
                "approved Component 1 or Component 2 output."
            ),
            payload=json.loads(SIMULATED_INPUT.read_text(encoding="utf-8")),
        )
    if fixture_id == "defect-scenarios":
        return SimulatedFixture(
            fixture_id=fixture_id,
            classification="SIMULATED_C4_FIXTURE",
            notice=(
                "SIMULATED Component 4 defect scenarios authored by the C3 implementer. "
                "Expected scopes are not independently reviewed and are not a benchmark."
            ),
            payload=json.loads(
                (FIXTURE_DIRECTORY / "c4_defect_scenarios.json").read_text(encoding="utf-8")
            ),
        )
    if fixture_id == "stack-criteria":
        return SimulatedFixture(
            fixture_id=fixture_id,
            classification="SIMULATED_CRITERIA",
            notice=(
                "SIMULATED manual stack-selection criteria and evidence references. They "
                "are caller-supplied and unverified."
            ),
            payload=build_simulated_stack_criteria().model_dump(mode="json"),
        )
    raise ApplicationError(
        [
            ErrorDetail(
                code="UNKNOWN_DEMO_FIXTURE",
                field="fixture_id",
                message=f"Unknown fixture. Available fixtures: {', '.join(FIXTURE_IDS)}.",
            )
        ],
        status_code=status.HTTP_404_NOT_FOUND,
    )


def preview_file(
    verifier: ManifestVerificationService, request: CodePreviewRequest
) -> CodePreviewResponse:
    """Return display-only text of one manifest file after full manifest verification."""
    path = PurePosixPath(request.relative_path)
    if (
        "\\" in request.relative_path
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != request.relative_path
    ):
        raise ApplicationError(
            [
                ErrorDetail(
                    code="UNSAFE_PREVIEW_PATH",
                    field="relative_path",
                    message="The preview path must be a safe relative POSIX path.",
                )
            ],
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    workspace = verifier.verify(request.manifest, request.workspace_relative_path)
    record = next(
        (item for item in request.manifest.files if item.relative_path == request.relative_path),
        None,
    )
    if record is None:
        raise ApplicationError(
            [
                ErrorDetail(
                    code="PREVIEW_FILE_NOT_IN_MANIFEST",
                    field="relative_path",
                    message="Only files listed in the verified manifest can be previewed.",
                )
            ],
            status_code=status.HTTP_404_NOT_FOUND,
        )
    raw = workspace.joinpath(*path.parts).read_bytes()
    truncated = len(raw) > MAX_PREVIEW_BYTES
    text = raw[:MAX_PREVIEW_BYTES].decode("utf-8", errors="replace")
    return CodePreviewResponse(
        relative_path=record.relative_path,
        artifact_type=record.artifact_type,
        origin=record.origin,
        sha256=record.sha256,
        size_bytes=record.size_bytes,
        truncated=truncated,
        content=text,
    )


def load_workspace_run(
    settings: Settings, request: WorkspaceRunRequest
) -> GenerationRunResult:
    """Read the stored manifest of an existing workspace after full verification.

    The scoped-regeneration result names the new workspace but does not return its
    manifest; this lets the dashboard preview patched files through the same verified,
    display-only preview path. Read-only; nothing is executed or written.
    """
    relative = request.workspace_relative_path
    path = PurePosixPath(relative)
    root = settings.generated_workspace_root.resolve()
    if (
        "\\" in relative
        or path.is_absolute()
        or ".." in path.parts
        or ":" in path.parts[0]
        or path.as_posix() != relative
    ):
        raise ApplicationError(
            [
                ErrorDetail(
                    code="UNSAFE_WORKSPACE_PATH",
                    field="workspace_relative_path",
                    message="Workspace path must be a safe relative POSIX path.",
                )
            ],
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    workspace = root.joinpath(*path.parts).resolve()
    manifest_path = workspace / "artifact-manifest.json"
    if not workspace.is_relative_to(root) or not manifest_path.is_file():
        raise ApplicationError(
            [
                ErrorDetail(
                    code="GENERATION_WORKSPACE_NOT_FOUND",
                    field="workspace_relative_path",
                    message="No generated workspace with a manifest exists at that path.",
                )
            ],
            status_code=status.HTTP_404_NOT_FOUND,
        )
    try:
        manifest = GenerationManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exception:
        raise ApplicationError(
            [
                ErrorDetail(
                    code="INVALID_STORED_MANIFEST",
                    field="workspace_relative_path",
                    message="The workspace manifest is missing or invalid.",
                )
            ],
            status_code=status.HTTP_409_CONFLICT,
        ) from exception
    ManifestVerificationService(root).verify(manifest, relative)
    return GenerationRunResult(
        workspace_relative_path=relative,
        manifest_relative_path=f"{relative}/artifact-manifest.json",
        manifest=manifest,
    )


async def create_defective_baseline(settings: Settings) -> DefectiveBaseline:
    """Generate a real run whose service module is the simulated defective fixture."""
    buggy_source = (FIXTURE_DIRECTORY / "buggy_task_service.js").read_text(encoding="utf-8")
    request = build_simulated_request(GenerationMode.LOCAL_LLM).model_copy(
        update={"workspace_name": DEMO_BASELINE_WORKSPACE_NAME}
    )
    client = SimulatedModelClient([model_output(SERVICE_PATH, buggy_source)])
    run = await CodeGenerationService(settings.generated_workspace_root, client).generate(request)
    traceability = TraceabilityService(
        verifier=ManifestVerificationService(settings.generated_workspace_root),
        builder=TraceabilityGraphBuilder(),
        store=SQLiteTraceabilityStore(settings.traceability_store_path),
    )
    snapshot = traceability.create(
        GraphCreateRequest(
            manifest=run.manifest,
            workspace_relative_path=run.workspace_relative_path,
        )
    )
    return DefectiveBaseline(
        notice=(
            "SIMULATED baseline. The generation service, manifest, and graph are real, but "
            "the service module is a deliberately defective test-double output, not Ollama "
            "output. The defect is injected for the demonstration."
        ),
        injected_defect_module=SERVICE_PATH,
        generation_run=run,
        design_context=request.design_context,
        graph_snapshot=snapshot,
    )


def mock_repair_client() -> SimulatedModelClient:
    """Deterministic MOCK repair model: always answers with the repaired service fixture."""
    repaired = (FIXTURE_DIRECTORY / "repaired_task_service.js").read_text(encoding="utf-8")
    return SimulatedModelClient([model_output(SERVICE_PATH, repaired)])
