"""Tests for isolated TeamSocLo Claude experimental code-generation workflow."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from intelise_c3.contracts.generation import (
    CodeGenerationRequest,
    GenerationMode,
    ProvisionalApprovalStatus,
    ProvisionalStackApproval,
)
from intelise_c3.contracts.provisional_input import ProvisionalInputPackage
from intelise_c3.contracts.stack_selection import (
    ArchitectureStyle,
    BackendRuntime,
    BackendTechnology,
    CriterionEvidence,
    FrontendTechnology,
    SelectionEvidence,
    StackSelectionCriteria,
    StackSelectionRequest,
    TeamProficiency,
)
from intelise_c3.core.config import Settings
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.generation import ArtifactOrigin
from intelise_c3.domain.llm import (
    LLMGenerationParameters,
    LLMInferenceMetadata,
    LLMInferenceRequest,
    LLMInferenceResponse,
    TeamSocLoResponseMetadata,
)
from intelise_c3.generation.templates import template_task_service
from intelise_c3.main import create_app
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService
from intelise_c3.services.stack_selection import StackSelectionService
from intelise_c3.generation.evidence import verify_manifest_evidence

FIXTURES = Path(__file__).parent / "fixtures" / "simulated"
VALID_TASK_SERVICE_CONTENT = template_task_service().content.strip()


class MockClaudeClient:
    """Mock TeamSocLo Claude client for isolated tests."""

    def __init__(self, response_text: str | None = None) -> None:
        self.response_text = response_text or json.dumps({
            "path": "backend/src/services/taskService.js",
            "content": VALID_TASK_SERVICE_CONTENT,
        })
        self.call_count = 0
        self.captured_requests: list[LLMInferenceRequest] = []

    async def generate(self, request: LLMInferenceRequest) -> LLMInferenceResponse:
        self.call_count += 1
        self.captured_requests.append(request)
        return LLMInferenceResponse(
            output_text=self.response_text,
            metadata=LLMInferenceMetadata(
                provider="teamsoclo-claude",
                configured_model_identifier="claude-haiku-4-5",
                response_model_identifier="claude-haiku-4-5",
                prompt_template_version=request.prompt_template_version,
                generation_parameters=LLMGenerationParameters(
                    temperature=0.0,
                    timeout_seconds=60.0,
                    max_tokens=4096,
                ),
                client_inference_latency_ms=150.0,
                response=TeamSocLoResponseMetadata(
                    id="msg_mock_001",
                    model="claude-haiku-4-5",
                    input_tokens=150,
                    output_tokens=300,
                    total_tokens=450,
                ),
            ),
        )


class FailingMockClaudeClient:
    async def generate(self, _request: LLMInferenceRequest) -> LLMInferenceResponse:
        raise ApplicationError(
            [ErrorDetail(code="TEAMSOCLO_REQUEST_TIMEOUT", field="teamsoclo", message="Timed out")],
            status_code=504,
        )


def _build_request(fixture_stem: str, mode: GenerationMode) -> CodeGenerationRequest:
    payload = json.loads((FIXTURES / f"{fixture_stem}_input_package.json").read_text(encoding="utf-8"))
    package = ProvisionalInputPackage.model_validate(payload)
    generation = InputValidationService().validate(package)
    design = DesignUnderstandingService().build(generation)
    evidence = CriterionEvidence(reference="EXP-TEST-EVIDENCE", confidence=1.0)
    criteria = StackSelectionCriteria(
        required_frontend=FrontendTechnology.REACT,
        required_backend=BackendTechnology.NODE_JS,
        architecture_style=ArchitectureStyle.REST_SPA,
        team_proficiency=TeamProficiency(react=0.8, angular=0.5, node_js=0.8, spring_boot=0.5),
        available_backend_runtimes=(BackendRuntime.NODE,),
        supports_static_spa=True,
        evidence=SelectionEvidence(
            requirements=evidence, architecture=evidence, team=evidence, deployment=evidence
        ),
    )
    report = StackSelectionService().select(StackSelectionRequest(design_context=design, criteria=criteria))
    return CodeGenerationRequest(
        generation_context=generation,
        design_context=design,
        stack_selection_report=report,
        stack_approval=ProvisionalStackApproval(
            status=ProvisionalApprovalStatus.APPROVED_FOR_MVP_GENERATION,
            approval_reference="EXP-TEST-APPROVAL",
            approved_by="TEST-RESEARCHER",
            acknowledges_provisional_policy=True,
        ),
        mode=mode,
        workspace_name=f"test-{fixture_stem}",
    )


def test_standard_endpoint_rejects_experimental_claude_mode():
    """Verify POST /api/v1/generation-runs strictly rejects EXPERIMENTAL_CLAUDE."""
    app = create_app()
    client = TestClient(app)
    req = _build_request("task_management", GenerationMode.EXPERIMENTAL_CLAUDE)
    response = client.post("/api/v1/generation-runs", json=req.model_dump(mode="json"))

    assert response.status_code == 400
    errors = response.json().get("errors", [])
    assert any(e.get("code") == "EXPERIMENTAL_MODE_REJECTED" for e in errors)


def test_claude_endpoint_forbidden_when_experiment_disabled():
    """Verify POST /api/v1/experiments/claude-generation is 403 when TEAMSOCLO_EXPERIMENT_ENABLED=false."""
    app = create_app()
    app.state.settings = Settings(teamsoclo_experiment_enabled=False)
    client = TestClient(app)
    req = _build_request("task_management", GenerationMode.EXPERIMENTAL_CLAUDE)
    response = client.post("/api/v1/experiments/claude-generation", json=req.model_dump(mode="json"))

    assert response.status_code == 403
    errors = response.json().get("errors", [])
    assert any(e.get("code") == "EXPERIMENT_DISABLED" for e in errors)


@pytest.mark.anyio
async def test_claude_experiment_task_generation_success(tmp_path: Path):
    """Verify successful end-to-end experimental generation for legacy task profile."""
    mock_claude = MockClaudeClient()
    service = CodeGenerationService(
        workspace_root=tmp_path,
        llm_client=mock_claude,
    )
    req = _build_request("task_management", GenerationMode.EXPERIMENTAL_CLAUDE)
    result = await service.generate(req)

    # 1. Verify workspace isolation
    assert result.workspace_relative_path.startswith("experiments/")
    workspace_disk = tmp_path / result.workspace_relative_path
    assert (workspace_disk / "backend" / "src" / "services" / "taskService.js").exists()
    assert (workspace_disk / "artifact-manifest.json").exists()

    # 2. Verify manifest and origin separation
    manifest = result.manifest
    assert manifest.generation_mode == GenerationMode.EXPERIMENTAL_CLAUDE
    assert manifest.llm_inference is not None
    assert manifest.llm_inference.provider == "teamsoclo-claude"
    assert manifest.llm_inference.response.total_tokens == 450

    task_file_record = next(f for f in manifest.files if f.relative_path == "backend/src/services/taskService.js")
    assert task_file_record.origin == ArtifactOrigin.EXPERIMENTAL_CLAUDE

    # 3. Verify evidence integrity
    verify_manifest_evidence(manifest)
    assert mock_claude.call_count == 1


@pytest.mark.anyio
async def test_claude_experiment_dynamic_student_generation_success(tmp_path: Path):
    """Verify dynamic C1/C2 project (Student Management) generates via experimental Claude."""
    student_service_code = """// Student Service
export function createStudentService(repository) {
  const fail = (statusCode, code, message) => {
    const error = new Error(message);
    error.statusCode = statusCode;
    error.code = code;
    throw error;
  };
  return {
    list: async () => repository.list(),
    create: async (input) => {
      const id = globalThis.crypto.randomUUID();
      const item = { ...input, id };
      return repository.create(item);
    },
    update: async (id, changes) => {
      if (!id || typeof id !== 'string') fail(400, 'INVALID_STUDENT_INPUT', 'Invalid id');
      const found = await repository.findById(id);
      if (!found) fail(404, 'STUDENT_NOT_FOUND', 'Student not found');
      return repository.update(id, changes);
    },
    remove: async (id) => {
      if (!id || typeof id !== 'string') fail(400, 'INVALID_STUDENT_INPUT', 'Invalid id');
      const found = await repository.findById(id);
      if (!found) fail(404, 'STUDENT_NOT_FOUND', 'Student not found');
      return repository.remove(id);
    },
  };
}
"""
    mock_claude = MockClaudeClient(
        response_text=json.dumps({
            "path": "backend/src/services/studentService.js",
            "content": student_service_code,
        })
    )
    service = CodeGenerationService(
        workspace_root=tmp_path,
        llm_client=mock_claude,
    )
    req = _build_request("student_management", GenerationMode.EXPERIMENTAL_CLAUDE)
    result = await service.generate(req)

    assert result.workspace_relative_path.startswith("experiments/")
    manifest = result.manifest
    assert manifest.generation_mode == GenerationMode.EXPERIMENTAL_CLAUDE
    assert manifest.llm_inference.provider == "teamsoclo-claude"

    student_file = next(f for f in manifest.files if f.relative_path == "backend/src/services/studentService.js")
    assert student_file.origin == ArtifactOrigin.EXPERIMENTAL_CLAUDE
    verify_manifest_evidence(manifest)


@pytest.mark.anyio
async def test_claude_failure_does_not_fall_back_to_ollama(tmp_path: Path):
    """Verify that failure of Claude fails explicitly and NEVER calls Ollama."""
    failing_claude = FailingMockClaudeClient()
    service = CodeGenerationService(
        workspace_root=tmp_path,
        llm_client=failing_claude,
    )
    req = _build_request("task_management", GenerationMode.EXPERIMENTAL_CLAUDE)

    with pytest.raises(ApplicationError) as exc_info:
        await service.generate(req)

    assert exc_info.value.status_code == 504
    assert exc_info.value.errors[0].code == "TEAMSOCLO_REQUEST_TIMEOUT"
