"""Tests for controlled React + Node.js MVP generation and its manifest."""

import asyncio
from hashlib import sha256
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
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.design_context import DesignContext
from intelise_c3.domain.generation import (
    ArtifactOrigin,
    TraceRelationType,
    TraceResolutionStatus,
    TraceReviewStatus,
)
from intelise_c3.domain.generation_context import GenerationContext
from intelise_c3.domain.llm import (
    LLMGenerationParameters,
    LLMInferenceMetadata,
    LLMInferenceRequest,
    LLMInferenceResponse,
    OllamaResponseMetadata,
)
from intelise_c3.domain.stack_selection import StackSelectionReport
from intelise_c3.generation.evidence import canonical_sha256, verify_manifest_evidence
from intelise_c3.generation.templates import (
    DB_TASK_COMPLETED_COLUMN,
    DB_TASK_ID_COLUMN,
    DB_TASK_TITLE_COLUMN,
    DB_TASKS_TABLE,
    TASK_REPOSITORY_SEAM,
    task_management_templates,
    template_task_service,
)
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService
from intelise_c3.services.stack_selection import StackSelectionService

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "simulated"
    / "task_management_input_package.json"
)
VALID_MODEL_MODULE = template_task_service().content.strip()


class StubLLMClient:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.requests: list[LLMInferenceRequest] = []

    async def generate(self, request: LLMInferenceRequest) -> LLMInferenceResponse:
        self.requests.append(request)
        return LLMInferenceResponse(
            output_text=self.output_text,
            metadata=LLMInferenceMetadata(
                configured_model_identifier="qwen2.5-coder:3b",
                response_model_identifier="qwen2.5-coder:3b",
                prompt_template_version=request.prompt_template_version,
                generation_parameters=LLMGenerationParameters(
                    temperature=0.0,
                    num_ctx=4096,
                    timeout_seconds=120.0,
                ),
                client_inference_latency_ms=12.5,
                response=OllamaResponseMetadata(
                    created_at="2026-10-13T00:00:00Z",
                    done=True,
                    done_reason="stop",
                    eval_count=120,
                ),
            ),
        )


class FailingLLMClient:
    async def generate(self, _request: LLMInferenceRequest) -> LLMInferenceResponse:
        raise AssertionError("TEMPLATE_ONLY mode must not call the LLM client.")


class UnavailableLLMClient:
    async def generate(self, _request: LLMInferenceRequest) -> LLMInferenceResponse:
        raise ApplicationError(
            [
                ErrorDetail(
                    code="OLLAMA_SERVICE_UNAVAILABLE",
                    field="ollama",
                    message="The local test service is unavailable.",
                )
            ],
            status_code=503,
        )


@pytest.fixture
def task_contexts() -> tuple[GenerationContext, DesignContext]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    package = ProvisionalInputPackage.model_validate(payload)
    generation = InputValidationService().validate(package)
    return generation, DesignUnderstandingService().build(generation)


def _selection_report(
    design_context: DesignContext,
    *,
    frontend: FrontendTechnology = FrontendTechnology.REACT,
    backend: BackendTechnology = BackendTechnology.NODE_JS,
) -> StackSelectionReport:
    runtime = (
        BackendRuntime.NODE
        if backend is BackendTechnology.NODE_JS
        else BackendRuntime.JVM
    )
    evidence = CriterionEvidence(reference="SIMULATED-GENERATION-EVIDENCE", confidence=1.0)
    criteria = StackSelectionCriteria(
        required_frontend=frontend,
        required_backend=backend,
        architecture_style=ArchitectureStyle.REST_SPA,
        team_proficiency=TeamProficiency(
            react=0.8,
            angular=0.8,
            node_js=0.8,
            spring_boot=0.8,
        ),
        available_backend_runtimes=(runtime,),
        supports_static_spa=True,
        evidence=SelectionEvidence(
            requirements=evidence,
            architecture=evidence,
            team=evidence,
            deployment=evidence,
        ),
    )
    return StackSelectionService().select(
        StackSelectionRequest(design_context=design_context, criteria=criteria)
    )


def _approval(
    status: ProvisionalApprovalStatus = (
        ProvisionalApprovalStatus.APPROVED_FOR_MVP_GENERATION
    ),
    *,
    acknowledged: bool = True,
) -> ProvisionalStackApproval:
    return ProvisionalStackApproval(
        status=status,
        approval_reference="SIMULATED-RESEARCHER-STACK-APPROVAL-001",
        approved_by="SIMULATED-RESEARCHER",
        acknowledges_provisional_policy=acknowledged,
    )


def _request(
    generation: GenerationContext,
    design: DesignContext,
    *,
    mode: GenerationMode = GenerationMode.LOCAL_LLM,
    report: StackSelectionReport | None = None,
    approval: ProvisionalStackApproval | None = None,
) -> CodeGenerationRequest:
    return CodeGenerationRequest(
        generation_context=generation,
        design_context=design,
        stack_selection_report=report or _selection_report(design),
        stack_approval=approval or _approval(),
        mode=mode,
        workspace_name="task-management-test",
    )


def _model_output(path: str = "backend/src/services/taskService.js", content: str = VALID_MODEL_MODULE) -> str:
    return json.dumps({"path": path, "content": content})


def test_valid_local_llm_generation_writes_manifest_and_preserves_identities(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    llm_client = StubLLMClient(_model_output())
    service = CodeGenerationService(tmp_path / "workspaces", llm_client)

    result = asyncio.run(service.generate(_request(generation, design)))

    workspace = tmp_path / "workspaces" / Path(result.workspace_relative_path)
    manifest_path = workspace / "artifact-manifest.json"
    service_path = workspace / "backend/src/services/taskService.js"
    assert manifest_path.is_file()
    assert service_path.read_text(encoding="utf-8").strip() == VALID_MODEL_MODULE
    assert result.manifest.generation_mode == "LOCAL_LLM"
    assert result.manifest.execution_status == "NOT_EXECUTED"
    assert result.manifest.llm_inference is not None
    assert result.manifest.llm_inference.prompt_template_version == (
        "react-node-task-service-v4"
    )
    assert result.manifest.source.requirement_ids == (
        "REQ-TASK-001",
        "REQ-TASK-002",
        "REQ-TASK-003",
    )
    assert result.manifest.source.uml_ids == (
        "UML-TASK-CLASS-001",
        "UML-TASK-SEQUENCE-001",
    )
    assert result.manifest.source.design_anchor_ids == (
        "ANCHOR-TASK-001",
        "ANCHOR-TASK-002",
        "ANCHOR-TASK-003",
    )
    service_record = next(
        item
        for item in result.manifest.files
        if item.relative_path == "backend/src/services/taskService.js"
    )
    assert service_record.origin is ArtifactOrigin.LOCAL_LLM
    assert service_record.test_seam_ids == (TASK_REPOSITORY_SEAM,)
    assert llm_client.requests[0].structured_output_schema is not None
    assert "REQ-TASK-001" in llm_client.requests[0].messages[1].content


def test_manifest_file_hashes_and_overall_digest_match_written_artifacts(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    result = asyncio.run(
        CodeGenerationService(
            tmp_path / "workspaces", StubLLMClient(_model_output())
        ).generate(_request(generation, design))
    )
    workspace = tmp_path / "workspaces" / Path(result.workspace_relative_path)
    aggregate = sha256()
    for record in result.manifest.files:
        content = (workspace / Path(record.relative_path)).read_bytes()
        assert sha256(content).hexdigest() == record.sha256
        assert len(content) == record.size_bytes
        aggregate.update(record.relative_path.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(record.sha256.encode("ascii"))
        aggregate.update(b"\n")
    assert aggregate.hexdigest() == result.manifest.artifact_digest_sha256


def test_task_model_sql_and_openapi_fields_are_consistent(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    result = asyncio.run(
        CodeGenerationService(tmp_path / "workspaces", None).generate(
            _request(generation, design, mode=GenerationMode.TEMPLATE_ONLY)
        )
    )
    workspace = tmp_path / "workspaces" / Path(result.workspace_relative_path)
    service_source = (workspace / "backend/src/services/taskService.js").read_text(
        encoding="utf-8"
    )
    sql_source = (workspace / "backend/src/db/schema.sql").read_text(
        encoding="utf-8"
    )
    openapi_source = (workspace / "api/openapi.yaml").read_text(encoding="utf-8")

    assert "const task = { id, title: title.trim(), completed: false };" in service_source
    assert all(field in sql_source for field in ("id TEXT", "title TEXT", "completed INTEGER"))
    assert "created_at" not in sql_source.casefold()
    assert "required: [id, title, completed]" in openapi_source
    assert "id: {type: string, format: uuid}" in openapi_source
    assert "title: {type: string, minLength: 1}" in openapi_source
    assert "completed: {type: boolean}" in openapi_source

    database = result.manifest.database_references[0]
    assert database.persistence_mode == "SCRIPT_ONLY"
    assert database.runtime_repository_mode == "IN_MEMORY"
    assert tuple(column.name for column in database.tables[0].columns) == (
        "id",
        "title",
        "completed",
    )
    assert tuple(column.column_id for column in database.tables[0].columns) == (
        DB_TASK_ID_COLUMN,
        DB_TASK_TITLE_COLUMN,
        DB_TASK_COMPLETED_COLUMN,
    )


def test_run_evidence_binds_inputs_prompt_model_and_artifacts(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    request = _request(generation, design)
    client = StubLLMClient(_model_output())
    result = asyncio.run(
        CodeGenerationService(tmp_path / "workspaces", client).generate(request)
    )
    evidence = result.manifest.run_evidence

    assert verify_manifest_evidence(result.manifest)
    assert evidence.input_hashes.generation_context_sha256 == canonical_sha256(generation)
    assert evidence.input_hashes.design_context_sha256 == canonical_sha256(design)
    assert evidence.input_hashes.stack_selection_report_sha256 == canonical_sha256(
        request.stack_selection_report
    )
    assert evidence.input_hashes.approval_input_sha256 == canonical_sha256(
        request.stack_approval
    )
    assert evidence.input_hashes.prompt_text_sha256 is not None
    assert evidence.input_hashes.prompt_request_sha256 == canonical_sha256(
        client.requests[0]
    )
    assert evidence.prompt_template_version == "react-node-task-service-v4"
    assert evidence.generator_version == "react-node-task-mvp-v2"
    assert evidence.template_set_version == "react-node-task-scaffold-v2"
    assert evidence.authenticity_claim is False


def test_altering_bound_evidence_invalidates_verification(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    result = asyncio.run(
        CodeGenerationService(tmp_path / "workspaces", None).generate(
            _request(generation, design, mode=GenerationMode.TEMPLATE_ONLY)
        )
    )
    altered_evidence = result.manifest.run_evidence.model_copy(
        update={"template_set_version": "tampered-template-version"}
    )
    altered_manifest = result.manifest.model_copy(
        update={"run_evidence": altered_evidence}
    )

    assert verify_manifest_evidence(result.manifest)
    assert not verify_manifest_evidence(altered_manifest)
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})


def test_traceability_is_precise_and_exposes_structured_identities(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    result = asyncio.run(
        CodeGenerationService(tmp_path / "workspaces", None).generate(
            _request(generation, design, mode=GenerationMode.TEMPLATE_ONLY)
        )
    )
    records = {record.relative_path: record for record in result.manifest.files}

    assert len(records) == 18
    assert records["README.md"].requirement_ids == ()
    assert records["frontend/src/components/TaskForm.jsx"].requirement_ids == (
        "REQ-TASK-001",
    )
    assert records["backend/src/services/taskService.js"].requirement_ids == (
        "REQ-TASK-001",
        "REQ-TASK-002",
        "REQ-TASK-003",
    )
    assert records["backend/src/repositories/taskRepository.js"].requirement_ids == (
        "REQ-TASK-003",
    )
    assert records["api/openapi.yaml"].api_operation_ids == (
        "API-OP-TASK-LIST",
        "API-OP-TASK-CREATE",
        "API-OP-TASK-UPDATE",
        "API-OP-TASK-DELETE",
    )
    assert records["backend/src/db/schema.sql"].database_entity_ids == (
        DB_TASKS_TABLE,
        DB_TASK_ID_COLUMN,
        DB_TASK_TITLE_COLUMN,
        DB_TASK_COMPLETED_COLUMN,
    )
    assert result.manifest.source.requirement_uml_anchors == design.requirement_uml_anchors
    assert result.manifest.source.ui_artifacts == design.ui_artifacts

    links = result.manifest.traceability.links
    assert {link.relation_type for link in links}.issuperset(
        {
            TraceRelationType.DERIVED_FROM,
            TraceRelationType.IMPLEMENTS,
            TraceRelationType.EXPOSES,
            TraceRelationType.PERSISTS_TO,
            TraceRelationType.VERIFIED_BY,
        }
    )
    ui_links = [link for link in links if link.target_entity_type.value == "UI_ARTIFACT"]
    assert ui_links
    assert all(
        link.resolution_status is TraceResolutionStatus.UNRESOLVED
        and link.review_status is TraceReviewStatus.REVIEW_REQUIRED
        for link in ui_links
    )
    persistence_link = next(
        link for link in links if link.relation_type is TraceRelationType.PERSISTS_TO
    )
    assert persistence_link.target_id == DB_TASKS_TABLE
    assert persistence_link.resolution_status is TraceResolutionStatus.UNRESOLVED
    assert "IN_MEMORY" in persistence_link.provenance.details


def test_unclassified_requirement_is_review_required_not_falsely_attributed(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    altered_requirement = generation.requirements[0].model_copy(
        update={"title": "Users need task behavior"}
    )
    requirements = (altered_requirement, *generation.requirements[1:])
    altered_generation = generation.model_copy(update={"requirements": requirements})
    altered_design = design.model_copy(update={"requirements": requirements})
    request = _request(
        altered_generation,
        altered_design,
        mode=GenerationMode.TEMPLATE_ONLY,
        report=_selection_report(altered_design),
    )

    result = asyncio.run(
        CodeGenerationService(tmp_path / "workspaces", None).generate(request)
    )

    assert all(
        "REQ-TASK-001" not in record.requirement_ids
        for record in result.manifest.files
    )
    unresolved = [
        link
        for link in result.manifest.traceability.links
        if link.source_id == "REQ-TASK-001"
        and link.target_entity_type.value == "GENERATION_RUN"
    ]
    assert len(unresolved) == 1
    assert unresolved[0].resolution_status is TraceResolutionStatus.UNRESOLVED
    assert unresolved[0].review_status is TraceReviewStatus.REVIEW_REQUIRED


def test_generated_scaffold_has_minimum_static_safety_controls() -> None:
    artifacts = {item.relative_path: item.content for item in task_management_templates()}
    artifacts["backend/src/services/taskService.js"] = template_task_service().content
    backend_package = json.loads(artifacts["backend/package.json"])
    frontend_package = json.loads(artifacts["frontend/package.json"])

    assert "CORS_ALLOWED_ORIGIN" in artifacts["backend/src/app.js"]
    assert "cors({ origin: allowedOrigin" in artifacts["backend/src/app.js"]
    assert "statusCode = 400" in artifacts["backend/src/controllers/taskController.js"]
    assert "typeof request.body.title !== 'string'" in artifacts[
        "backend/src/controllers/taskController.js"
    ]
    assert "typeof request.body.completed !== 'boolean'" in artifacts[
        "backend/src/controllers/taskController.js"
    ]
    assert "globalThis.crypto.randomUUID()" in artifacts[
        "backend/src/services/taskService.js"
    ]
    assert "TASK_NOT_FOUND" in artifacts["backend/src/services/taskService.js"]
    assert "IN_MEMORY" in artifacts["backend/src/repositories/taskRepository.js"]
    assert "npm audit" in artifacts["README.md"]
    assert "No dependency audit result is claimed" in artifacts["README.md"]
    for package in (backend_package, frontend_package):
        direct_versions = {
            **package.get("dependencies", {}),
            **package.get("devDependencies", {}),
        }
        assert all(
            version and not version.startswith(("^", "~")) and version != "latest"
            for version in direct_versions.values()
        )


def test_only_accepted_model_artifact_receives_local_llm_origin(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    result = asyncio.run(
        CodeGenerationService(
            tmp_path / "workspaces", StubLLMClient(_model_output())
        ).generate(_request(generation, design))
    )
    local_files = [
        record.relative_path
        for record in result.manifest.files
        if record.origin is ArtifactOrigin.LOCAL_LLM
    ]
    template_files = [
        record for record in result.manifest.files if record.origin is ArtifactOrigin.TEMPLATE
    ]

    assert local_files == ["backend/src/services/taskService.js"]
    assert len(template_files) == 17


def test_failed_final_manifest_write_never_publishes_success_record(
    monkeypatch,
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    original_replace = Path.replace

    def fail_manifest_publish(path: Path, target: Path) -> Path:
        if path.name == "artifact-manifest.json.pending":
            raise OSError("simulated atomic manifest publication failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_manifest_publish)
    workspace_root = tmp_path / "workspaces"

    with pytest.raises(ApplicationError) as captured:
        asyncio.run(
            CodeGenerationService(workspace_root, None).generate(
                _request(generation, design, mode=GenerationMode.TEMPLATE_ONLY)
            )
        )

    assert captured.value.errors[0].code == "WORKSPACE_WRITE_FAILED"
    assert not tuple(workspace_root.rglob("artifact-manifest.json"))


def test_template_only_is_explicit_and_never_calls_llm(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    result = asyncio.run(
        CodeGenerationService(tmp_path / "workspaces", FailingLLMClient()).generate(
            _request(generation, design, mode=GenerationMode.TEMPLATE_ONLY)
        )
    )
    service_record = next(
        item
        for item in result.manifest.files
        if item.relative_path == "backend/src/services/taskService.js"
    )
    assert result.manifest.generation_mode == "TEMPLATE_ONLY"
    assert result.manifest.llm_inference is None
    assert service_record.origin is ArtifactOrigin.TEMPLATE


def test_local_llm_failure_does_not_fall_back_to_templates(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    workspace_root = tmp_path / "workspaces"

    with pytest.raises(ApplicationError) as captured:
        asyncio.run(
            CodeGenerationService(workspace_root, UnavailableLLMClient()).generate(
                _request(generation, design)
            )
        )

    assert captured.value.errors[0].code == "OLLAMA_SERVICE_UNAVAILABLE"
    assert not workspace_root.exists()


@pytest.mark.parametrize(
    "field, value",
    (
        ("project_id", "PROJECT-OTHER"),
        ("srs_version", "SRS-OTHER"),
        ("uml_version", "UML-OTHER"),
        ("generation_context_version", "99.0"),
    ),
)
def test_mismatched_generation_context_is_rejected(
    field: str,
    value: str,
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    mismatched = design.model_copy(update={field: value})

    with pytest.raises(ApplicationError) as captured:
        asyncio.run(
            CodeGenerationService(tmp_path, StubLLMClient(_model_output())).generate(
                _request(generation, mismatched)
            )
        )

    assert captured.value.status_code == 409
    assert "GENERATION_CONTEXT_MISMATCH" in {
        error.code for error in captured.value.errors
    }


def test_missing_design_references_are_rejected(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    incomplete = design.model_copy(update={"requirement_uml_anchors": ()})

    with pytest.raises(ApplicationError) as captured:
        asyncio.run(
            CodeGenerationService(tmp_path, StubLLMClient(_model_output())).generate(
                _request(generation, incomplete)
            )
        )

    assert "MISSING_GENERATION_DESIGN_REFERENCE" in {
        error.code for error in captured.value.errors
    }


def test_stack_report_for_another_design_context_is_rejected(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    report = _selection_report(design).model_copy(
        update={"design_context_version": "different-design-version"}
    )

    with pytest.raises(ApplicationError) as captured:
        asyncio.run(
            CodeGenerationService(tmp_path, StubLLMClient(_model_output())).generate(
                _request(generation, design, report=report)
            )
        )

    assert "STACK_REPORT_CONTEXT_MISMATCH" in {
        error.code for error in captured.value.errors
    }


def test_unsupported_selected_stack_is_not_substituted(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    unsupported = _selection_report(
        design,
        frontend=FrontendTechnology.ANGULAR,
        backend=BackendTechnology.NODE_JS,
    )

    with pytest.raises(ApplicationError) as captured:
        asyncio.run(
            CodeGenerationService(tmp_path, StubLLMClient(_model_output())).generate(
                _request(generation, design, report=unsupported)
            )
        )

    assert captured.value.errors[0].code == "GENERATOR_NOT_IMPLEMENTED"


def test_missing_stack_approval_is_rejected(
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    pending = _approval(ProvisionalApprovalStatus.PENDING, acknowledged=False)

    with pytest.raises(ApplicationError) as captured:
        asyncio.run(
            CodeGenerationService(tmp_path, StubLLMClient(_model_output())).generate(
                _request(generation, design, approval=pending)
            )
        )

    assert captured.value.errors[0].code == "STACK_APPROVAL_REQUIRED"


@pytest.mark.parametrize(
    "output",
    ("", "not-json", json.dumps({"path": "backend/src/services/taskService.js", "content": ""})),
)
def test_empty_or_malformed_model_output_is_rejected(
    output: str,
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    with pytest.raises(ApplicationError) as captured:
        asyncio.run(
            CodeGenerationService(tmp_path, StubLLMClient(output)).generate(
                _request(generation, design)
            )
        )

    assert captured.value.status_code == 502
    assert captured.value.errors[0].code == "INVALID_GENERATED_MODEL_OUTPUT"


@pytest.mark.parametrize(
    "unsafe_path",
    ("../escape.js", "/absolute.js", "backend\\escape.js", "C:/escape.js"),
)
def test_unsafe_model_paths_are_rejected(
    unsafe_path: str,
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    with pytest.raises(ApplicationError) as captured:
        asyncio.run(
            CodeGenerationService(
                tmp_path, StubLLMClient(_model_output(path=unsafe_path))
            ).generate(_request(generation, design))
        )

    assert captured.value.errors[0].code == "UNSAFE_GENERATED_PATH"
    assert not (tmp_path / "escape.js").exists()


def test_conflicting_artifact_paths_are_rejected(tmp_path: Path) -> None:
    service = CodeGenerationService(tmp_path, None)
    artifact = task_management_templates()[0]

    with pytest.raises(ApplicationError) as captured:
        service._validate_artifact_set((artifact, artifact))

    assert captured.value.errors[0].code == "CONFLICTING_GENERATED_PATH"


def test_symbolic_link_workspace_root_is_rejected(
    monkeypatch,
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts
    workspace_root = tmp_path / "workspaces"
    original_is_symlink = Path.is_symlink

    def report_workspace_root_as_symlink(path: Path) -> bool:
        return path == workspace_root or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", report_workspace_root_as_symlink)

    with pytest.raises(ApplicationError) as captured:
        asyncio.run(
            CodeGenerationService(
                workspace_root,
                StubLLMClient(_model_output()),
            ).generate(_request(generation, design))
        )

    assert captured.value.errors[0].code == "UNSAFE_WORKSPACE_ROOT"


@pytest.mark.parametrize(
    "content, expected_code",
    (
        (
            "import { helper } from './helper.js';\n" + VALID_MODEL_MODULE,
            "UNSAFE_GENERATED_CONTENT",
        ),
        (
            VALID_MODEL_MODULE.replace(
                "repository.update(id, { completed: changes.completed })",
                "repository.update(changes)",
            ),
            "INVALID_GENERATED_MODULE",
        ),
        (
            VALID_MODEL_MODULE.replace("completed: false", "completed: true"),
            "INVALID_GENERATED_MODULE",
        ),
        (
            VALID_MODEL_MODULE.replace(
                "return repository.update(id, { completed: changes.completed });",
                "Object.assign(existing, changes); return repository.update(id, { completed: changes.completed });",
            ),
            "UNSAFE_GENERATED_CONTENT",
        ),
    ),
)
def test_unsafe_or_incompatible_model_module_is_rejected(
    content: str,
    expected_code: str,
    tmp_path: Path,
    task_contexts: tuple[GenerationContext, DesignContext],
) -> None:
    generation, design = task_contexts

    with pytest.raises(ApplicationError) as captured:
        asyncio.run(
            CodeGenerationService(
                tmp_path,
                StubLLMClient(_model_output(content=content)),
            ).generate(_request(generation, design))
        )

    assert captured.value.errors[0].code == expected_code


def test_generation_route_is_exposed_without_affecting_health(
    client: TestClient,
) -> None:
    openapi = client.get("/api/v1/openapi.json")
    health = client.get("/api/v1/health")

    assert openapi.status_code == 200
    assert "/api/v1/generation-runs" in openapi.json()["paths"]
    assert health.status_code == 200
