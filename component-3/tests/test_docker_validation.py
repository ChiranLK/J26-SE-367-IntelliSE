"""Unit tests for Stage 2 preflight and restricted Docker policy."""

import asyncio
import json
from pathlib import Path

import pytest

from intelise_c3.docker_validation import (
    DockerPreflightError,
    inspect_generated_workspace,
    restricted_runtime_command,
    smoke_plan,
)
from intelise_c3.scripts.validate_dynamic_crud_docker import build_simulated_request
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.crud_spec import CrudApplicationSpecBuilder
from intelise_c3.traceability.verification import ManifestVerificationService


def _generated(tmp_path: Path, domain: str):
    request = build_simulated_request(domain)
    result = asyncio.run(CodeGenerationService(tmp_path, None).generate(request))
    workspace = tmp_path / Path(result.workspace_relative_path)
    ManifestVerificationService(tmp_path).verify(
        result.manifest,
        result.workspace_relative_path,
    )
    spec = CrudApplicationSpecBuilder().build(request.design_context)
    return result, workspace, spec


@pytest.mark.parametrize(
    "domain",
    ("student_management", "library_management", "inventory_management"),
)
def test_preflight_accepts_all_supported_generated_domains(
    tmp_path: Path,
    domain: str,
) -> None:
    result, workspace, spec = _generated(tmp_path, domain)

    report = inspect_generated_workspace(workspace, result.manifest, spec)

    assert report.policy_version == "C3_DOCKER_PREFLIGHT_V1"
    assert report.inspected_file_count == len(result.manifest.files)
    assert report.api_operation_count == len(spec.entities) * 4
    assert report.database_table_count == len(spec.entities)


def test_preflight_rejects_unreviewed_dependency(tmp_path: Path) -> None:
    result, workspace, spec = _generated(tmp_path, "student_management")
    path = workspace / "backend/package.json"
    package = json.loads(path.read_text(encoding="utf-8"))
    package["dependencies"]["left-pad"] = "1.3.0"
    path.write_text(json.dumps(package), encoding="utf-8")

    with pytest.raises(DockerPreflightError, match="allowlist"):
        inspect_generated_workspace(workspace, result.manifest, spec)


def test_preflight_rejects_non_string_dependency_version(tmp_path: Path) -> None:
    result, workspace, spec = _generated(tmp_path, "student_management")
    path = workspace / "backend/package.json"
    package = json.loads(path.read_text(encoding="utf-8"))
    package["dependencies"]["express"] = 4
    path.write_text(json.dumps(package), encoding="utf-8")

    with pytest.raises(DockerPreflightError, match="allowlist"):
        inspect_generated_workspace(workspace, result.manifest, spec)


def test_preflight_rejects_package_lifecycle_script(tmp_path: Path) -> None:
    result, workspace, spec = _generated(tmp_path, "student_management")
    path = workspace / "frontend/package.json"
    package = json.loads(path.read_text(encoding="utf-8"))
    package["scripts"]["postinstall"] = "node install.js"
    path.write_text(json.dumps(package), encoding="utf-8")

    with pytest.raises(DockerPreflightError, match="forbidden lifecycle"):
        inspect_generated_workspace(workspace, result.manifest, spec)


def test_preflight_rejects_openapi_operation_mismatch(tmp_path: Path) -> None:
    result, workspace, spec = _generated(tmp_path, "student_management")
    path = workspace / "api/openapi.yaml"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["paths"]["/api/v1/students"]["post"]["operationId"] = "wrongOperation"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(DockerPreflightError, match="operationId mismatch"):
        inspect_generated_workspace(workspace, result.manifest, spec)


def test_runtime_command_enforces_restricted_container_policy() -> None:
    command = restricted_runtime_command("example:validation", "example-validation")
    text = " ".join(command)

    assert "--network none" in text
    assert "--read-only" in command
    assert "--cap-drop ALL" in text
    assert "no-new-privileges:true" in command
    assert "--pids-limit 128" in text
    assert "--memory 256m" in text
    assert "--cpus 0.50" in text
    assert "--user 1000:1000" in text
    assert "--privileged" not in command
    assert "--volume" not in command
    assert "--mount" not in command


def test_tracked_dockerfile_builds_and_tests_as_non_root() -> None:
    component_root = Path(__file__).resolve().parents[1]
    dockerfile = (component_root / "docker-validation" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert dockerfile.count("USER node") == 3
    assert dockerfile.count("npm audit --audit-level=high") == 2
    assert "npm run build" in dockerfile
    assert "npm test" in dockerfile
    assert "node:24-bookworm-slim@sha256:" in dockerfile
    assert "/var/run/docker.sock" not in dockerfile


def test_library_smoke_plan_contains_both_entities(tmp_path: Path) -> None:
    _result, _workspace, spec = _generated(tmp_path, "library_management")
    plan = smoke_plan(spec)

    assert [item["name"] for item in plan["entities"]] == ["Book", "Member"]
    assert [item["collectionPath"] for item in plan["entities"]] == [
        "/api/v1/books",
        "/api/v1/members",
    ]

