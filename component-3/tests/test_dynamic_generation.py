"""End-to-end Python tests for three inputs using the same CRUD renderer."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

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
from intelise_c3.domain.generation import (
    ArtifactOrigin,
    TraceResolutionStatus,
    TraceReviewStatus,
)
from intelise_c3.core.errors import ApplicationError
from intelise_c3.generation.crud_templates import (
    DYNAMIC_GENERATOR_VERSION,
    DYNAMIC_TEMPLATE_SET_VERSION,
    DYNAMIC_TRACEABILITY_MAPPING_POLICY_VERSION,
)
from intelise_c3.generation.evidence import verify_manifest_evidence
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService
from intelise_c3.services.stack_selection import StackSelectionService
from intelise_c3.services.scoped_regeneration import ScopedRegenerationService
from intelise_c3.services.structural_verification import StructuralVerificationService
from intelise_c3.traceability.verification import ManifestVerificationService
from intelise_c3.traceability.builder import TraceabilityGraphBuilder
from intelise_c3.contracts.structural_verification import StructuralVerificationRequest

FIXTURES = Path(__file__).parent / "fixtures" / "simulated"


def _request(name: str) -> CodeGenerationRequest:
    payload = json.loads(
        (FIXTURES / f"{name}_input_package.json").read_text(encoding="utf-8")
    )
    generation = InputValidationService().validate(
        ProvisionalInputPackage.model_validate(payload)
    )
    design = DesignUnderstandingService().build(generation)
    evidence = CriterionEvidence(
        reference=f"SIMULATED-{name.upper()}-STACK-EVIDENCE",
        confidence=1.0,
        uncertainty_notes="Simulated Stage 1 generator fixture only.",
    )
    report = StackSelectionService().select(
        StackSelectionRequest(
            design_context=design,
            criteria=StackSelectionCriteria(
                required_frontend=FrontendTechnology.REACT,
                required_backend=BackendTechnology.NODE_JS,
                architecture_style=ArchitectureStyle.REST_SPA,
                team_proficiency=TeamProficiency(
                    react=0.8,
                    angular=0.5,
                    node_js=0.8,
                    spring_boot=0.5,
                ),
                available_backend_runtimes=(BackendRuntime.NODE,),
                supports_static_spa=True,
                preferred_backend_runtime=BackendRuntime.NODE,
                evidence=SelectionEvidence(
                    requirements=evidence,
                    architecture=evidence,
                    team=evidence,
                    deployment=evidence,
                ),
            ),
        )
    )
    return CodeGenerationRequest(
        generation_context=generation,
        design_context=design,
        stack_selection_report=report,
        stack_approval=ProvisionalStackApproval(
            status=ProvisionalApprovalStatus.APPROVED_FOR_MVP_GENERATION,
            approval_reference=f"SIMULATED-{name.upper()}-APPROVAL",
            approved_by="SIMULATED-STAGE1-RESEARCHER",
            acknowledges_provisional_policy=True,
        ),
        mode=GenerationMode.TEMPLATE_ONLY,
        workspace_name=name.replace("_", "-"),
    )


def _generate(tmp_path: Path, name: str):
    root = tmp_path / "workspaces"
    result = asyncio.run(CodeGenerationService(root, None).generate(_request(name)))
    workspace = root / Path(result.workspace_relative_path)
    ManifestVerificationService(root).verify(
        result.manifest, result.workspace_relative_path
    )
    return result, workspace


@pytest.mark.parametrize(
    ("fixture", "expected_paths", "route", "table", "field_markers"),
    (
        (
            "student_management",
            (
                "frontend/src/components/StudentForm.jsx",
                "backend/src/services/studentService.js",
                "backend/src/repositories/studentRepository.js",
            ),
            "/api/v1/students",
            "students",
            ("name", "age", "gpa", "enrolled", "birthDate"),
        ),
        (
            "library_management",
            (
                "frontend/src/components/BookForm.jsx",
                "frontend/src/components/MemberForm.jsx",
                "backend/src/services/bookService.js",
                "backend/src/services/memberService.js",
            ),
            "/api/v1/books",
            "books",
            ("title", "publishedDate", "available", "borrowLimit"),
        ),
        (
            "inventory_management",
            (
                "frontend/src/components/InventoryItemForm.jsx",
                "backend/src/services/inventoryItemService.js",
                "backend/src/repositories/inventoryItemRepository.js",
            ),
            "/api/v1/inventory-items",
            "inventory_items",
            ("name", "quantity", "unitPrice", "active", "stockDate"),
        ),
    ),
)
def test_same_generator_creates_domain_specific_projects(
    tmp_path: Path,
    fixture: str,
    expected_paths: tuple[str, ...],
    route: str,
    table: str,
    field_markers: tuple[str, ...],
) -> None:
    result, workspace = _generate(tmp_path, fixture)
    manifest = result.manifest
    paths = {record.relative_path for record in manifest.files}

    assert set(expected_paths).issubset(paths)
    assert verify_manifest_evidence(manifest)
    assert manifest.run_evidence.generator_version == DYNAMIC_GENERATOR_VERSION
    assert manifest.run_evidence.template_set_version == DYNAMIC_TEMPLATE_SET_VERSION
    assert (
        manifest.traceability.mapping_policy_version
        == DYNAMIC_TRACEABILITY_MAPPING_POLICY_VERSION
    )
    assert all(record.origin is ArtifactOrigin.TEMPLATE for record in manifest.files)
    assert manifest.execution_status == "NOT_EXECUTED"
    assert route in {operation.route_path for reference in manifest.api_references for operation in reference.operations}
    assert table in {item.name for reference in manifest.database_references for item in reference.tables}

    combined = "\n".join(
        (workspace / Path(record.relative_path)).read_text(encoding="utf-8")
        for record in manifest.files
    )
    assert all(marker in combined for marker in field_markers)
    assert "Task Management" not in combined
    assert "INVALID_CRUD_INPUT" not in combined


def test_three_domains_have_distinct_paths_routes_tables_and_digests(tmp_path: Path) -> None:
    generated = {
        name: _generate(tmp_path, name)[0].manifest
        for name in (
            "student_management",
            "library_management",
            "inventory_management",
        )
    }

    assert len({item.artifact_digest_sha256 for item in generated.values()}) == 3
    assert {
        tuple(operation.route_path for reference in item.api_references for operation in reference.operations)
        for item in generated.values()
    }.__len__() == 3
    assert {
        tuple(table.name for reference in item.database_references for table in reference.tables)
        for item in generated.values()
    } == {("students",), ("books", "members"), ("inventory_items",)}


def test_reusable_frontend_styles_align_boolean_fields_and_support_mobile(tmp_path: Path) -> None:
    result, workspace = _generate(tmp_path, "student_management")
    styles = (workspace / "frontend/src/styles.css").read_text(encoding="utf-8")
    form = (workspace / "frontend/src/components/StudentForm.jsx").read_text(
        encoding="utf-8"
    )

    assert result.manifest.generation_run_id
    assert 'className="boolean-field"' in form
    assert ".boolean-field { display: flex; align-items: center;" in styles
    assert "@media (max-width: 640px)" in styles


def test_dynamic_manifest_preserves_source_ids_and_review_required_links(tmp_path: Path) -> None:
    result, _workspace = _generate(tmp_path, "student_management")
    manifest = result.manifest
    form = next(
        item
        for item in manifest.files
        if item.relative_path == "frontend/src/components/StudentForm.jsx"
    )

    assert form.requirement_ids == (
        "REQ-STUDENT-001",
        "REQ-STUDENT-002",
        "REQ-STUDENT-003",
    )
    assert form.uml_ids == ("UML-STUDENT-CLASS-001",)
    assert form.design_anchor_ids == (
        "ANCHOR-STUDENT-001",
        "ANCHOR-STUDENT-002",
        "ANCHOR-STUDENT-003",
    )
    assert manifest.source.c1_approval_provenance_ref == "SIMULATED-C1-STUDENT-APPROVAL-001"
    ui_links = [
        link
        for link in manifest.traceability.links
        if link.target_id == "UI-STUDENT-WIREFRAME-001"
    ]
    assert ui_links
    assert all(link.resolution_status is TraceResolutionStatus.UNRESOLVED for link in ui_links)
    assert all(link.review_status is TraceReviewStatus.REVIEW_REQUIRED for link in ui_links)
    persistence_links = [
        link
        for link in manifest.traceability.links
        if link.provenance.mapping_rule_id == "CRUD_SPEC_RUNTIME_SQL_REVIEW_V1"
    ]
    assert len(persistence_links) == 1
    assert persistence_links[0].review_status is TraceReviewStatus.REVIEW_REQUIRED

    graph = TraceabilityGraphBuilder().build(manifest)
    assert graph.source.requirement_ids == manifest.source.requirement_ids
    assert graph.source.uml_ids == manifest.source.uml_ids
    assert graph.generation_run_id == manifest.generation_run_id
    assert graph.artifact_digest_sha256 == manifest.artifact_digest_sha256
    assert any(
        link.review_status is TraceReviewStatus.REVIEW_REQUIRED
        for link in graph.links
    )


def test_dynamic_local_llm_mode_is_rejected_without_template_fallback(tmp_path: Path) -> None:
    request = _request("student_management").model_copy(
        update={"mode": GenerationMode.LOCAL_LLM}
    )

    with pytest.raises(ApplicationError) as captured:
        asyncio.run(CodeGenerationService(tmp_path, None).generate(request))

    assert captured.value.errors[0].code == "DYNAMIC_LOCAL_LLM_NOT_IMPLEMENTED"


def test_dynamic_structural_verification_is_available_for_student_runs(
    tmp_path: Path,
) -> None:
    from intelise_c3.domain.structural_verification import StructuralFindingStatus

    result, _workspace = _generate(tmp_path, "student_management")
    verifier = ManifestVerificationService(tmp_path / "workspaces")
    report = StructuralVerificationService(verifier).verify(
        StructuralVerificationRequest(
            manifest=result.manifest,
            workspace_relative_path=result.workspace_relative_path,
            design_context=_request("student_management").design_context,
        )
    )
    assert report.summary.fail_count == 0
    assert report.overall_status in {
        StructuralFindingStatus.PASS,
        StructuralFindingStatus.REVIEW_REQUIRED,
    }

