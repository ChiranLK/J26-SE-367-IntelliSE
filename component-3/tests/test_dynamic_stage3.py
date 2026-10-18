"""Stage 3: dynamic structural verification and scoped regeneration."""

from __future__ import annotations

import asyncio
import json
from hashlib import sha256
from pathlib import Path

import pytest

from intelise_c3.contracts.defect_report import DefectItem, DefectReport
from intelise_c3.domain.generation import GenerationManifest
from intelise_c3.contracts.scoped_regeneration import ScopedRegenerationRequest
from intelise_c3.contracts.structural_verification import StructuralVerificationRequest
from intelise_c3.contracts.traceability import GraphCreateRequest
from intelise_c3.domain.scoped_regeneration import ImpactSelectionStatus, RegenerationStatus
from intelise_c3.domain.structural_verification import StructuralFindingStatus
from intelise_c3.regeneration.dynamic_patch_policy import build_patchable_modules
from intelise_c3.scripts.scoped_regeneration_experiment import (
    SimulatedModelClient,
    build_traceability,
    model_output,
)
from intelise_c3.services.scoped_regeneration import ScopedRegenerationService
from intelise_c3.services.structural_verification import StructuralVerificationService
from intelise_c3.traceability.impact import ImpactSelector
from intelise_c3.generation.evidence import compute_evidence_digest
from intelise_c3.traceability.verification import ManifestVerificationService

from tests.test_dynamic_generation import _generate, _request


def _rebind_manifest(result, workspace: Path, *, files=None):
    manifest = result.manifest
    bound_files = tuple(files if files is not None else manifest.files)
    aggregate = sha256()
    for record in sorted(bound_files, key=lambda item: item.relative_path):
        aggregate.update(record.relative_path.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(record.sha256.encode("ascii"))
        aggregate.update(b"\n")
    artifact_digest = aggregate.hexdigest()
    evidence = manifest.run_evidence
    evidence_digest = compute_evidence_digest(
        generation_run_id=manifest.generation_run_id,
        input_hashes=evidence.input_hashes,
        prompt_template_version=evidence.prompt_template_version,
        generator_version=evidence.generator_version,
        template_set_version=evidence.template_set_version,
        llm_inference=manifest.llm_inference,
        artifact_digest_sha256=artifact_digest,
    )
    updated = manifest.model_copy(
        update={
            "files": bound_files,
            "artifact_digest_sha256": artifact_digest,
            "run_evidence": evidence.model_copy(
                update={"evidence_digest_sha256": evidence_digest}
            ),
        }
    )
    (workspace / "artifact-manifest.json").write_text(
        json.dumps(updated.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result.model_copy(update={"manifest": updated})


def _rewrite_artifact(result, workspace: Path, relative_path: str, transform):
    path = workspace / relative_path
    updated_text = transform(path.read_text(encoding="utf-8"))
    path.write_text(updated_text, encoding="utf-8", newline="\n")
    content = path.read_bytes()
    files = tuple(
        record.model_copy(
            update={"sha256": sha256(content).hexdigest(), "size_bytes": len(content)}
        )
        if record.relative_path == relative_path
        else record
        for record in result.manifest.files
    )
    return _rebind_manifest(result, workspace, files=files)


def _workspace_root(tmp_path: Path) -> Path:
    return tmp_path / "workspaces"


def _structural(domain: str, tmp_path: Path):
    result, workspace = _generate(tmp_path, domain)
    service = StructuralVerificationService(ManifestVerificationService(_workspace_root(tmp_path)))
    report = service.verify(
        StructuralVerificationRequest(
            manifest=result.manifest,
            workspace_relative_path=result.workspace_relative_path,
            design_context=_request(domain).design_context,
        )
    )
    return result, workspace, report


def test_dynamic_structural_verification_passes_for_student(tmp_path: Path) -> None:
    _result, _workspace, report = _structural("student_management", tmp_path)
    assert report.summary.fail_count == 0
    assert report.overall_status in {
        StructuralFindingStatus.PASS,
        StructuralFindingStatus.REVIEW_REQUIRED,
    }
    assert any(finding.rule_id == "CRUD_REQUIRED_MODULES_V1" for finding in report.findings)


def test_dynamic_structural_verification_fails_on_missing_module(tmp_path: Path) -> None:
    result, workspace, report = _structural("student_management", tmp_path)
    kept = tuple(
        record
        for record in result.manifest.files
        if record.relative_path != "backend/src/services/studentService.js"
    )
    assert report.summary.fail_count == 0
    (workspace / "backend/src/services/studentService.js").unlink()
    broken = _rebind_manifest(result, workspace, files=kept)
    service = StructuralVerificationService(ManifestVerificationService(_workspace_root(tmp_path)))
    broken_report = service.verify(
        StructuralVerificationRequest(
            manifest=broken.manifest,
            workspace_relative_path=result.workspace_relative_path,
            design_context=_request("student_management").design_context,
        )
    )
    assert broken_report.summary.fail_count >= 1


def test_dynamic_structural_verification_fails_on_openapi_mismatch(tmp_path: Path) -> None:
    result, workspace, _report = _structural("student_management", tmp_path)
    broken = _rewrite_artifact(
        result,
        workspace,
        "api/openapi.yaml",
        lambda source: source.replace("API-OP-STUDENT-LIST", "API-OP-STUDENT-WRONG"),
    )
    service = StructuralVerificationService(ManifestVerificationService(_workspace_root(tmp_path)))
    report = service.verify(
        StructuralVerificationRequest(
            manifest=broken.manifest,
            workspace_relative_path=result.workspace_relative_path,
            design_context=_request("student_management").design_context,
        )
    )
    assert report.summary.fail_count >= 1


def test_dynamic_structural_verification_fails_on_sql_spec_mismatch(
    tmp_path: Path,
) -> None:
    result, workspace, _report = _structural("inventory_management", tmp_path)
    broken = _rewrite_artifact(
        result,
        workspace,
        "backend/src/db/schema.sql",
        lambda source: source.replace("inventory_items", "wrong_inventory_table"),
    )
    service = StructuralVerificationService(ManifestVerificationService(_workspace_root(tmp_path)))
    report = service.verify(
        StructuralVerificationRequest(
            manifest=broken.manifest,
            workspace_relative_path=result.workspace_relative_path,
            design_context=_request("inventory_management").design_context,
        )
    )
    assert report.summary.fail_count >= 1


def test_library_patch_allowlist_is_per_entity() -> None:
    spec = _request("library_management").design_context
    from intelise_c3.services.crud_spec import CrudApplicationSpecBuilder

    built = CrudApplicationSpecBuilder().build(spec)
    modules = build_patchable_modules(built)
    assert "backend/src/services/bookService.js" in modules
    assert "backend/src/services/memberService.js" in modules
    assert "backend/src/services/studentService.js" not in modules


def _defect_for_service(
    result,
    *,
    hook_ref: str,
    service_path: str,
    operation_id: str,
    requirement_id: str,
) -> DefectReport:
    return DefectReport(
        source_classification="SIMULATED_C4_FIXTURE",
        defect_report_id="SIM-STAGE3-DEFECT",
        reported_at_utc="2026-10-19T00:00:00+00:00",
        source_generation_run_id=result.manifest.generation_run_id,
        source_artifact_digest_sha256=result.manifest.artifact_digest_sha256,
        source_graph_version=1,
        defects=(
            DefectItem.model_validate(
                {
                    "defect_id": "SIM-DEF-STAGE3-001",
                    "category": "BUSINESS_LOGIC",
                    "severity": "HIGH",
                    "title": "SIMULATED service defect for Stage 3",
                    "affected_requirement_ids": [requirement_id],
                    "failing_tests": [
                        {
                            "test_case_id": "SIM-TC-STAGE3",
                            "hook_type": "TEST_FILE",
                            "hook_ref": hook_ref,
                        }
                    ],
                    "api_operation_ids": [operation_id],
                    "location": {"relative_path": service_path, "symbol": "update"},
                    "evidence": {
                        "observed_behavior": "SIMULATED incorrect behavior.",
                        "expected_behavior": "SIMULATED expected behavior.",
                    },
                    "explanation": "SIMULATED C4-style explanation; not independent C4 output.",
                }
            ),
        ),
    )


def _operation_id(result, suffix: str) -> str:
    for reference in result.manifest.api_references:
        for operation in reference.operations:
            if operation.operation_id.endswith(suffix):
                return operation.operation_id
    raise AssertionError(f"operation suffix {suffix} not found")


@pytest.mark.parametrize(
    ("domain", "service_path", "test_hook", "req_id", "op_suffix"),
    [
        (
            "student_management",
            "backend/src/services/studentService.js",
            "backend/tests/studentService.test.js",
            "REQ-STUDENT-002",
            "UPDATE",
        ),
        (
            "inventory_management",
            "backend/src/services/inventoryItemService.js",
            "backend/tests/inventoryItemService.test.js",
            "REQ-INVENTORY-002",
            "UPDATE",
        ),
    ],
)
def test_dynamic_scoped_regeneration_preserves_unrelated_files(
    tmp_path: Path,
    domain: str,
    service_path: str,
    test_hook: str,
    req_id: str,
    op_suffix: str,
) -> None:
    root = _workspace_root(tmp_path)
    result, workspace = _generate(tmp_path, domain)
    traceability = build_traceability(root, tmp_path / "graphs.sqlite3")
    traceability.create(
        GraphCreateRequest(
            manifest=result.manifest,
            workspace_relative_path=result.workspace_relative_path,
        )
    )
    before = {
        record.relative_path: record.sha256 for record in result.manifest.files if record.relative_path != service_path
    }
    current = (workspace / service_path).read_text(encoding="utf-8")
    patched = current.replace("fail(404", "fail(409")  # force a real diff for mock patch
    client = SimulatedModelClient([model_output(service_path, patched)])
    service = ScopedRegenerationService(
        root,
        traceability,
        client,
        model_evidence_class="MOCKED_TEST_DOUBLE",
    )
    report = _defect_for_service(
        result,
        hook_ref=test_hook,
        service_path=service_path,
        operation_id=_operation_id(result, op_suffix),
        requirement_id=req_id,
    )
    outcome = asyncio.run(
        service.regenerate(
            ScopedRegenerationRequest(
                defect_report=report,
                manifest=result.manifest,
                workspace_relative_path=result.workspace_relative_path,
                design_context=_request(domain).design_context,
            )
        )
    )
    assert outcome.status is RegenerationStatus.PATCHED_PENDING_INDEPENDENT_RETEST
    assert outcome.artifact_versioning is not None
    new_workspace = root / Path(outcome.artifact_versioning.new_workspace_relative_path)
    new_manifest = GenerationManifest.model_validate_json(
        (new_workspace / "artifact-manifest.json").read_text(encoding="utf-8")
    )
    after = {record.relative_path: record.sha256 for record in new_manifest.files}
    for path, digest in before.items():
        assert after[path] == digest
    assert after[service_path] != before.get(service_path, "")


def test_library_book_defect_does_not_select_member_service(tmp_path: Path) -> None:
    root = _workspace_root(tmp_path)
    result, workspace = _generate(tmp_path, "library_management")
    traceability = build_traceability(root, tmp_path / "graphs.sqlite3")
    snapshot = traceability.create(
        GraphCreateRequest(
            manifest=result.manifest,
            workspace_relative_path=result.workspace_relative_path,
        )
    )
    spec = _request("library_management").design_context
    from intelise_c3.services.crud_spec import CrudApplicationSpecBuilder

    patchable = build_patchable_modules(CrudApplicationSpecBuilder().build(spec))
    report = _defect_for_service(
        result,
        hook_ref="backend/tests/bookService.test.js",
        service_path="backend/src/services/bookService.js",
        operation_id=_operation_id(result, "UPDATE"),
        requirement_id="REQ-BOOK-002",
    )
    impact = ImpactSelector(frozenset(patchable.keys())).select(
        snapshot=snapshot,
        manifest=result.manifest,
        report=report,
        report_sha256=sha256(report.model_dump_json().encode("utf-8")).hexdigest(),
    )
    assert impact.status is ImpactSelectionStatus.SELECTED
    paths = {module.relative_path for module in impact.selected_modules}
    assert "backend/src/services/bookService.js" in paths
    assert "backend/src/services/memberService.js" not in paths


def test_dynamic_scoped_regeneration_appends_graph_version(tmp_path: Path) -> None:
    root = _workspace_root(tmp_path)
    result, workspace = _generate(tmp_path, "student_management")
    traceability = build_traceability(root, tmp_path / "graphs.sqlite3")
    snapshot = traceability.create(
        GraphCreateRequest(
            manifest=result.manifest,
            workspace_relative_path=result.workspace_relative_path,
        )
    )
    service_path = "backend/src/services/studentService.js"
    current = (workspace / service_path).read_text(encoding="utf-8")
    patched = current.replace("fail(404", "fail(409")
    client = SimulatedModelClient([model_output(service_path, patched)])
    service = ScopedRegenerationService(
        root,
        traceability,
        client,
        model_evidence_class="MOCKED_TEST_DOUBLE",
    )
    report = _defect_for_service(
        result,
        hook_ref="backend/tests/studentService.test.js",
        service_path=service_path,
        operation_id=_operation_id(result, "UPDATE"),
        requirement_id="REQ-STUDENT-002",
    )
    outcome = asyncio.run(
        service.regenerate(
            ScopedRegenerationRequest(
                defect_report=report,
                manifest=result.manifest,
                workspace_relative_path=result.workspace_relative_path,
                design_context=_request("student_management").design_context,
            )
        )
    )
    assert outcome.status is RegenerationStatus.PATCHED_PENDING_INDEPENDENT_RETEST
    assert outcome.graph_versioning is not None
    assert outcome.graph_versioning.new_graph_version > snapshot.graph_version
    assert outcome.graph_versioning.base_graph_version == snapshot.graph_version
    assert outcome.graph_versioning.change_report is not None
    assert outcome.graph_versioning.change_report.artifacts.changed


def test_legacy_task_structural_verification_still_passes(tmp_path: Path) -> None:
    from intelise_c3.scripts.generate_task_mvp import build_simulated_request
    from intelise_c3.contracts.generation import GenerationMode
    from intelise_c3.services.code_generation import CodeGenerationService

    request = build_simulated_request(GenerationMode.TEMPLATE_ONLY)
    result = asyncio.run(CodeGenerationService(tmp_path / "task", None).generate(request))
    service = StructuralVerificationService(ManifestVerificationService(tmp_path / "task"))
    report = service.verify(
        StructuralVerificationRequest(
            manifest=result.manifest,
            workspace_relative_path=result.workspace_relative_path,
            design_context=request.design_context,
        )
    )
    assert report.summary.fail_count == 0
