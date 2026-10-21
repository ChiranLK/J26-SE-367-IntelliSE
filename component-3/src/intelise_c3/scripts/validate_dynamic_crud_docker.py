"""Generate and validate the simulated dynamic CRUD domains inside Docker only."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any
from uuid import uuid4

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
from intelise_c3.docker_validation import (
    DockerPreflightError,
    inspect_generated_workspace,
    restricted_runtime_command,
    smoke_plan,
)
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.crud_spec import CrudApplicationSpecBuilder
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService
from intelise_c3.services.stack_selection import StackSelectionService
from intelise_c3.traceability.verification import ManifestVerificationService

COMPONENT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = COMPONENT_ROOT / "tests" / "fixtures" / "simulated"
HARNESS_ROOT = COMPONENT_ROOT / "docker-validation"
OUTPUT_ROOT = COMPONENT_ROOT / ".stage2-validation"
DOMAINS = ("student_management", "library_management", "inventory_management")
DEFAULT_NODE_IMAGE = (
    "node:24-bookworm-slim@sha256:"
    "a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5"
)
BUILD_TIMEOUT_SECONDS = 600
COMMAND_TIMEOUT_SECONDS = 60


class DockerValidationFailure(RuntimeError):
    """One isolated validation step failed."""


def build_simulated_request(domain: str) -> CodeGenerationRequest:
    """Build one explicitly simulated request through the real C3 services."""
    fixture = FIXTURE_ROOT / f"{domain}_input_package.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    package = ProvisionalInputPackage.model_validate(payload)
    generation = InputValidationService().validate(package)
    design = DesignUnderstandingService().build(generation)
    evidence = CriterionEvidence(
        reference=f"SIMULATED-{domain.upper()}-DOCKER-VALIDATION",
        confidence=1.0,
        uncertainty_notes="Simulated Stage 2 Docker validation input only.",
    )
    selection = StackSelectionService().select(
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
        stack_selection_report=selection,
        stack_approval=ProvisionalStackApproval(
            status=ProvisionalApprovalStatus.APPROVED_FOR_MVP_GENERATION,
            approval_reference=f"SIMULATED-{domain.upper()}-STAGE2-APPROVAL",
            approved_by="SIMULATED-STAGE2-RESEARCHER",
            acknowledges_provisional_policy=True,
        ),
        mode=GenerationMode.TEMPLATE_ONLY,
        workspace_name="app",
    )


def _run(
    arguments: tuple[str, ...] | list[str],
    *,
    timeout: int,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(arguments),
            input=input_text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as exception:
        raise DockerValidationFailure(
            f"Command exceeded its {timeout}-second limit: {arguments[0]}"
        ) from exception


def _require_success(
    result: subprocess.CompletedProcess[str],
    *,
    label: str,
    log_path: Path,
) -> None:
    log_path.write_text(
        result.stdout + ("\n[stderr]\n" + result.stderr if result.stderr else ""),
        encoding="utf-8",
        newline="\n",
    )
    if result.returncode != 0:
        raise DockerValidationFailure(
            f"{label} failed with exit code {result.returncode}; see {log_path}."
        )


def _assert_docker_available() -> str:
    result = _run(
        ("docker", "version", "--format", "{{.Server.Version}}"),
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise DockerValidationFailure(
            "Docker Desktop Linux engine is unavailable: " + result.stderr.strip()
        )
    return result.stdout.strip()


def _assert_container_policy(container_name: str) -> dict[str, Any]:
    result = _run(
        ("docker", "inspect", container_name),
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise DockerValidationFailure("Cannot inspect the validation container.")
    inspected = json.loads(result.stdout)[0]
    host = inspected["HostConfig"]
    expected = {
        "Privileged": False,
        "ReadonlyRootfs": True,
        "NetworkMode": "none",
        "PidsLimit": 128,
        "Memory": 268435456,
    }
    observed = {name: host.get(name) for name in expected}
    if observed != expected:
        raise DockerValidationFailure(
            f"Runtime isolation policy mismatch: expected {expected}, observed {observed}."
        )
    if "ALL" not in (host.get("CapDrop") or []):
        raise DockerValidationFailure("Runtime container did not drop all capabilities.")
    if "no-new-privileges:true" not in (host.get("SecurityOpt") or []):
        raise DockerValidationFailure("Runtime container lacks no-new-privileges.")
    mounts = inspected.get("Mounts") or []
    if mounts:
        raise DockerValidationFailure("Runtime container unexpectedly has host mounts.")
    return {
        "privileged": False,
        "read_only_root": True,
        "network_mode": "none",
        "pids_limit": 128,
        "memory_bytes": 268435456,
        "capabilities_dropped": "ALL",
        "no_new_privileges": True,
        "host_mount_count": 0,
    }


async def _validate_domain(
    domain: str,
    session_root: Path,
    node_image: str,
    keep_images: bool,
) -> dict[str, Any]:
    domain_root = session_root / domain
    context_root = domain_root / "context"
    context_root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(HARNESS_ROOT, context_root / "harness")
    shutil.copy2(
        HARNESS_ROOT / "context.dockerignore",
        context_root / ".dockerignore",
    )

    request = build_simulated_request(domain)
    result = await CodeGenerationService(context_root, None).generate(request)
    workspace = context_root / Path(result.workspace_relative_path)
    ManifestVerificationService(context_root).verify(
        result.manifest,
        result.workspace_relative_path,
    )
    spec = CrudApplicationSpecBuilder().build(request.design_context)
    preflight = inspect_generated_workspace(workspace, result.manifest, spec)

    tag_suffix = session_root.name.removeprefix("stage2-").casefold()
    image = f"intelise-c3-{domain.replace('_', '-')}-validation:{tag_suffix}"
    container = f"intelise-c3-{domain.replace('_', '-')}-{tag_suffix}"
    app_path = Path(result.workspace_relative_path).as_posix()
    build_command = (
        "docker",
        "build",
        "--pull",
        "--progress",
        "plain",
        "--target",
        "runtime",
        "--memory",
        "1g",
        "--shm-size",
        "128m",
        "--ulimit",
        "nofile=1024:1024",
        "--build-arg",
        f"APP_PATH={app_path}",
        "--build-arg",
        f"NODE_IMAGE={node_image}",
        "--tag",
        image,
        "--file",
        str(context_root / "harness" / "Dockerfile"),
        str(context_root),
    )
    run_command = restricted_runtime_command(image, container)
    commands = {
        "build": list(build_command),
        "run": list(run_command),
        "smoke": [
            "docker",
            "exec",
            "-i",
            container,
            "node",
            "/opt/intelise-validator/api-smoke.mjs",
        ],
    }

    started = False
    try:
        build = _run(build_command, timeout=BUILD_TIMEOUT_SECONDS)
        _require_success(
            build,
            label=f"{domain} image build",
            log_path=domain_root / "docker-build.log",
        )
        image_inspect = _run(
            ("docker", "image", "inspect", image, "--format", "{{.Id}}|{{.Config.User}}"),
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        _require_success(
            image_inspect,
            label=f"{domain} image inspection",
            log_path=domain_root / "image-inspect.log",
        )
        image_id, configured_user = image_inspect.stdout.strip().split("|", 1)
        if configured_user != "node":
            raise DockerValidationFailure(
                f"{domain} runtime image is not configured for the non-root node user."
            )

        started_result = _run(run_command, timeout=COMMAND_TIMEOUT_SECONDS)
        _require_success(
            started_result,
            label=f"{domain} runtime start",
            log_path=domain_root / "docker-run.log",
        )
        started = True
        isolation = _assert_container_policy(container)
        plan = smoke_plan(spec)
        smoke = _run(
            commands["smoke"],
            timeout=COMMAND_TIMEOUT_SECONDS,
            input_text=json.dumps(plan),
        )
        _require_success(
            smoke,
            label=f"{domain} API smoke test",
            log_path=domain_root / "api-smoke.log",
        )
        smoke_result = json.loads(smoke.stdout)
        return {
            "domain": domain,
            "status": "PASS",
            "workspace": str(workspace.relative_to(COMPONENT_ROOT)),
            "generation_run_id": result.manifest.generation_run_id,
            "artifact_digest_sha256": result.manifest.artifact_digest_sha256,
            "evidence_digest_sha256": result.manifest.run_evidence.evidence_digest_sha256,
            "manifest_verified": True,
            "preflight": preflight.__dict__,
            "image": image,
            "image_id": image_id,
            "configured_user": configured_user,
            "isolation": isolation,
            "smoke": smoke_result,
            "commands": commands,
        }
    finally:
        if started:
            _run(("docker", "rm", "--force", container), timeout=COMMAND_TIMEOUT_SECONDS)
        if not keep_images:
            _run(("docker", "image", "rm", image), timeout=COMMAND_TIMEOUT_SECONDS)


async def run(domains: tuple[str, ...], node_image: str, keep_images: bool) -> int:
    docker_server_version = _assert_docker_available()
    session_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    session_root = OUTPUT_ROOT / f"stage2-{session_id}"
    session_root.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []

    for domain in domains:
        try:
            results.append(
                await _validate_domain(domain, session_root, node_image, keep_images)
            )
        except (DockerValidationFailure, DockerPreflightError, OSError, ValueError) as error:
            results.append(
                {
                    "domain": domain,
                    "status": "FAIL",
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            )

    report = {
        "report_version": "1.0",
        "classification": "SIMULATED_STAGE2_DOCKER_VALIDATION",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "docker_server_version": docker_server_version,
        "node_image": node_image,
        "images_retained": keep_images,
        "results": results,
    }
    report_path = session_root / "validation-report.json"
    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, indent=2))
    print(f"Validation report: {report_path}")
    return 0 if all(item["status"] == "PASS" for item in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate SIMULATED Student/Library/Inventory CRUD applications and "
            "validate them only in restricted Docker containers."
        )
    )
    parser.add_argument(
        "--domain",
        action="append",
        choices=DOMAINS,
        help="Validate only a selected domain; repeat for multiple domains.",
    )
    parser.add_argument("--node-image", default=DEFAULT_NODE_IMAGE)
    parser.add_argument(
        "--keep-images",
        action="store_true",
        help="Keep built validation images for an approved manual browser preview.",
    )
    arguments = parser.parse_args()
    domains = tuple(arguments.domain) if arguments.domain else DOMAINS
    raise SystemExit(asyncio.run(run(domains, arguments.node_image, arguments.keep_images)))


if __name__ == "__main__":
    main()
