"""Tests for deterministic, non-executing design-to-code verification."""

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from intelise_c3.contracts.generation import GenerationMode
from intelise_c3.contracts.structural_verification import StructuralVerificationRequest
from intelise_c3.core.config import get_settings
from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.structural_verification import StructuralFindingStatus
from intelise_c3.generation.evidence import compute_evidence_digest
from intelise_c3.main import create_app
from intelise_c3.scripts.generate_task_mvp import build_simulated_request
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.structural_verification import StructuralVerificationService
from intelise_c3.traceability.verification import ManifestVerificationService


FIXED_TIME = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def _generated_run(workspace_root: Path):
    request = build_simulated_request(GenerationMode.TEMPLATE_ONLY)
    result = asyncio.run(CodeGenerationService(workspace_root, None).generate(request))
    workspace = workspace_root / Path(result.workspace_relative_path)
    return request, result, workspace


def _service(workspace_root: Path) -> StructuralVerificationService:
    return StructuralVerificationService(
        ManifestVerificationService(workspace_root),
        clock=lambda: FIXED_TIME,
    )


def _verify(service, request, result):
    return service.verify(
        StructuralVerificationRequest(
            manifest=result.manifest,
            workspace_relative_path=result.workspace_relative_path,
            design_context=request.design_context,
        )
    )


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
        rag_evidence=evidence.rag,
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


def _finding(report, finding_id: str):
    return next(item for item in report.findings if item.finding_id == finding_id)


def test_valid_task_mvp_returns_pass_findings_and_review_limit(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    request, result, _workspace = _generated_run(root)

    report = _verify(_service(root), request, result)

    assert report.overall_status is StructuralFindingStatus.REVIEW_REQUIRED
    assert report.summary.fail_count == 0
    assert report.summary.pass_count == 8
    assert report.summary.review_required_count == 1
    assert _finding(report, "C3SV-ARCH-001").status is StructuralFindingStatus.PASS
    assert _finding(report, "C3SV-LIMIT-001").status is StructuralFindingStatus.REVIEW_REQUIRED
    assert report.execution_claim == "STATIC_INSPECTION_ONLY_NOT_EXECUTED"
    assert report.component4_claim is False


def test_report_preserves_source_identities_and_serializes_deterministically(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    request, result, _workspace = _generated_run(root)
    service = _service(root)

    first = _verify(service, request, result)
    second = _verify(service, request, result)

    assert first.project_id == request.design_context.project_id
    assert first.requirement_ids == result.manifest.source.requirement_ids
    assert first.uml_ids == result.manifest.source.uml_ids
    assert first.artifact_digest_sha256 == result.manifest.artifact_digest_sha256
    assert first.model_dump_json() == second.model_dump_json()
    assert all(finding.finding_id.startswith("C3SV-") for finding in first.findings)
    assert all(
        set(finding.requirement_ids).issubset(first.requirement_ids)
        and set(finding.uml_ids).issubset(first.uml_ids)
        for finding in first.findings
    )


def test_missing_openapi_operation_produces_machine_readable_failure(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    request, result, workspace = _generated_run(root)
    broken = _rewrite_artifact(
        result,
        workspace,
        "api/openapi.yaml",
        lambda source: source.replace("operationId: deleteTask", "operationId: wrongDelete"),
    )

    report = _verify(_service(root), request, broken)
    finding = _finding(report, "C3SV-API-001")

    assert report.overall_status is StructuralFindingStatus.FAIL
    assert finding.status is StructuralFindingStatus.FAIL
    assert "api/openapi.yaml" in finding.evidence_paths
    assert "API-OP-TASK-DELETE" in " ".join(finding.observed)
    assert finding.affected_module_ids


def test_direct_controller_repository_access_is_layer_violation(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    request, result, workspace = _generated_run(root)
    broken = _rewrite_artifact(
        result,
        workspace,
        "backend/src/controllers/taskController.js",
        lambda source: source + "\nconst forbidden = repository.list();\n",
    )

    report = _verify(_service(root), request, broken)
    finding = _finding(report, "C3SV-ARCH-001")

    assert finding.status is StructuralFindingStatus.FAIL
    assert "controller-direct-repository-access" in finding.observed


def test_repository_signature_mismatch_is_detected(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    request, result, workspace = _generated_run(root)
    broken = _rewrite_artifact(
        result,
        workspace,
        "backend/src/repositories/taskRepository.js",
        lambda source: source.replace("async update(id, changes)", "async update(changes)"),
    )

    report = _verify(_service(root), request, broken)
    finding = _finding(report, "C3SV-REPOSITORY-001")

    assert finding.status is StructuralFindingStatus.FAIL
    assert "repository-signature:update('id', 'changes')" in finding.observed


def test_missing_required_module_record_is_detected(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    request, result, workspace = _generated_run(root)
    files = tuple(
        record
        for record in result.manifest.files
        if record.relative_path != "frontend/src/api/tasks.js"
    )
    broken = _rebind_manifest(result, workspace, files=files)

    report = _verify(_service(root), request, broken)

    assert _finding(report, "C3SV-MODULE-001").status is StructuralFindingStatus.FAIL
    assert "missing:frontend/src/api/tasks.js" in _finding(
        report, "C3SV-MODULE-001"
    ).observed


def test_tampered_file_is_rejected_before_structural_checks(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    request, result, workspace = _generated_run(root)
    service_path = workspace / "backend/src/services/taskService.js"
    service_path.write_text(
        service_path.read_text(encoding="utf-8") + "\n// tampered\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ApplicationError) as captured:
        _verify(_service(root), request, result)

    assert captured.value.errors[0].code == "ARTIFACT_HASH_MISMATCH"


def test_unbound_design_context_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    request, result, _workspace = _generated_run(root)
    altered = request.design_context.model_copy(update={"project_id": "OTHER-PROJECT"})

    with pytest.raises(ApplicationError) as captured:
        _service(root).verify(
            StructuralVerificationRequest(
                manifest=result.manifest,
                workspace_relative_path=result.workspace_relative_path,
                design_context=altered,
            )
        )

    assert captured.value.errors[0].code == "DESIGN_CONTEXT_DIGEST_MISMATCH"


def test_structural_verification_endpoint_uses_existing_application(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    request, result, _workspace = _generated_run(root)
    get_settings.cache_clear()
    try:
        application = create_app()
        application.state.settings = SimpleNamespace(generated_workspace_root=root)
        with TestClient(application) as client:
            response = client.post(
                "/api/v1/structural-verifications",
                json=StructuralVerificationRequest(
                    manifest=result.manifest,
                    workspace_relative_path=result.workspace_relative_path,
                    design_context=request.design_context,
                ).model_dump(mode="json"),
            )
            assert response.status_code == 200
            assert response.json()["summary"]["fail_count"] == 0
            health = client.get("/api/v1/health")
            assert health.status_code == 200
            openapi = client.get("/api/v1/openapi.json")
            assert "/api/v1/structural-verifications" in openapi.json()["paths"]
    finally:
        get_settings.cache_clear()


def _hash_workspace(workspace: Path) -> dict[str, str]:
    return {
        path.relative_to(workspace).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
    }


def test_findings_reference_unique_ids_and_real_manifest_modules(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    request, result, _workspace = _generated_run(root)

    report = _verify(_service(root), request, result)

    file_ids = {record.file_id for record in result.manifest.files}
    paths = {record.relative_path for record in result.manifest.files}
    finding_ids = [finding.finding_id for finding in report.findings]
    assert len(finding_ids) == len(set(finding_ids)) == 9
    for finding in report.findings:
        assert finding.affected_module_ids
        assert set(finding.affected_module_ids).issubset(file_ids)
        assert set(finding.evidence_paths).issubset(paths)


def test_verification_is_read_only_and_never_claims_runtime_or_c4(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    request, result, workspace = _generated_run(root)
    before = _hash_workspace(workspace)

    report = _verify(_service(root), request, result)

    assert _hash_workspace(workspace) == before
    assert report.overall_status is not StructuralFindingStatus.PASS
    assert report.component4_claim is False
    assert report.execution_claim == "STATIC_INSPECTION_ONLY_NOT_EXECUTED"
    limit = _finding(report, "C3SV-LIMIT-001")
    assert limit.status is StructuralFindingStatus.REVIEW_REQUIRED
    assert "runtime" in limit.message and "Component 4" in limit.message


@pytest.mark.parametrize(
    ("relative_path", "appended", "violation"),
    [
        (
            "backend/src/routes/taskRoutes.js",
            "\nconst forbidden = service.list();\n",
            "routes-bypass-controller",
        ),
        (
            "backend/src/services/taskService.js",
            "\nimport { x } from '../controllers/taskController.js';\n",
            "service-bypasses-injected-boundaries",
        ),
        (
            "backend/src/repositories/taskRepository.js",
            "\nimport { x } from '../services/taskService.js';\n",
            "repository-depends-on-upper-layer",
        ),
        (
            "backend/src/controllers/taskController.js",
            "\nimport { x } from '../services/taskService.js';\n",
            "controller-bypasses-service-injection",
        ),
    ],
)
def test_each_forbidden_layer_dependency_fails_with_named_violation(
    tmp_path: Path,
    relative_path: str,
    appended: str,
    violation: str,
) -> None:
    root = tmp_path / "workspaces"
    request, result, workspace = _generated_run(root)
    broken = _rewrite_artifact(result, workspace, relative_path, lambda source: source + appended)

    report = _verify(_service(root), request, broken)
    finding = _finding(report, "C3SV-ARCH-001")
    module_id = next(
        record.file_id for record in broken.manifest.files if record.relative_path == relative_path
    )

    assert report.overall_status is StructuralFindingStatus.FAIL
    assert finding.status is StructuralFindingStatus.FAIL
    assert violation in finding.observed
    assert module_id in finding.affected_module_ids
    assert relative_path in finding.evidence_paths


def test_unsupported_stack_is_rejected_not_silently_verified(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    request, result, workspace = _generated_run(root)
    manifest = result.manifest.model_copy(update={"selected_stack_id": "angular-spring"})
    (workspace / "artifact-manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ApplicationError) as captured:
        _verify(_service(root), request, result.model_copy(update={"manifest": manifest}))

    assert captured.value.errors[0].code == "UNSUPPORTED_VERIFICATION_STACK"
    assert captured.value.status_code == 409


def test_manifest_not_matching_stored_workspace_manifest_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    request, result, _workspace = _generated_run(root)
    altered = result.manifest.model_copy(update={"selected_stack_id": "angular-spring"})

    with pytest.raises(ApplicationError) as captured:
        _verify(_service(root), request, result.model_copy(update={"manifest": altered}))

    assert captured.value.errors[0].code == "MANIFEST_PAYLOAD_MISMATCH"


def test_unsafe_workspace_path_is_rejected_by_endpoint(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    request, result, _workspace = _generated_run(root)
    get_settings.cache_clear()
    try:
        application = create_app()
        application.state.settings = SimpleNamespace(generated_workspace_root=root)
        with TestClient(application) as client:
            response = client.post(
                "/api/v1/structural-verifications",
                json=StructuralVerificationRequest(
                    manifest=result.manifest,
                    workspace_relative_path="../escape",
                    design_context=request.design_context,
                ).model_dump(mode="json"),
            )
            assert response.status_code == 422
    finally:
        get_settings.cache_clear()
