"""Isolated experiment script for TeamSocLo Claude code generation.

Runs the experimental Claude Haiku 4.5 code-generation workflow separately
from the official Ollama research runtime.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

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
from intelise_c3.core.errors import ApplicationError
from intelise_c3.llm.teamsoclo import TeamSocLoClaudeLLMClient
from intelise_c3.rag.runtime import RagRuntime
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService
from intelise_c3.services.stack_selection import StackSelectionService

COMPONENT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = COMPONENT_ROOT / "tests" / "fixtures" / "simulated"


def build_experiment_request(fixture_stem: str) -> CodeGenerationRequest:
    """Load and validate any dynamic C1/C2 project fixture for the experiment."""
    fixture_path = FIXTURES_DIR / f"{fixture_stem}_input_package.json"
    if not fixture_path.exists():
        raise FileNotFoundError(f"Simulated fixture not found: {fixture_path}")

    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    package = ProvisionalInputPackage.model_validate(payload)
    generation_context = InputValidationService().validate(package)
    design_context = DesignUnderstandingService().build(generation_context)

    evidence = CriterionEvidence(
        reference=f"EXP-CLAUDE-{fixture_stem.upper()}-EVIDENCE",
        confidence=1.0,
        uncertainty_notes="Experimental Claude code generation workflow",
    )
    criteria = StackSelectionCriteria(
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
    )
    report = StackSelectionService().select(
        StackSelectionRequest(
            design_context=design_context,
            criteria=criteria,
        )
    )

    return CodeGenerationRequest(
        generation_context=generation_context,
        design_context=design_context,
        stack_selection_report=report,
        stack_approval=ProvisionalStackApproval(
            status=ProvisionalApprovalStatus.APPROVED_FOR_MVP_GENERATION,
            approval_reference=f"EXP-CLAUDE-{fixture_stem.upper()}-APPROVAL",
            approved_by="EXPERIMENT-RESEARCHER",
            acknowledges_provisional_policy=True,
        ),
        mode=GenerationMode.EXPERIMENTAL_CLAUDE,
        workspace_name=f"claude-{fixture_stem}",
    )


async def run_experiment(fixture_stem: str) -> int:
    settings = Settings()
    if not settings.teamsoclo_experiment_enabled:
        print("Error: TEAMSOCLO_EXPERIMENT_ENABLED is false in settings.")
        print("To enable, set TEAMSOCLO_EXPERIMENT_ENABLED=true in backend environment.")
        return 1

    if not settings.teamsoclo_api_key or not settings.teamsoclo_api_key.strip():
        print("Error: TEAMSOCLO_API_KEY is missing or empty in backend environment.")
        return 1

    try:
        request = build_experiment_request(fixture_stem)
    except Exception as exc:
        print(f"Failed to prepare C1/C2 experiment request: {exc}")
        return 1

    client = TeamSocLoClaudeLLMClient(settings)
    service = CodeGenerationService(
        settings.generated_workspace_root,
        client,
        RagRuntime.from_settings(settings),
    )

    print(f"Starting isolated Claude experiment for fixture: {fixture_stem}...")
    print(f"Gateway: {settings.teamsoclo_base_url}")
    print(f"Configured Model: {settings.teamsoclo_model}")

    try:
        result = await service.generate(request)
    except ApplicationError as exception:
        error = exception.errors[0]
        print(f"Experiment generation failed [{error.code}]: {error.message}")
        return 1
    except Exception as exc:
        print(f"Unexpected error during experiment generation: {exc}")
        return 1

    workspace = settings.generated_workspace_root / Path(result.workspace_relative_path)
    manifest = result.manifest
    print("=" * 60)
    print("Isolated Claude Experiment Completed Successfully!")
    print(f"Mode: {manifest.generation_mode}")
    print(f"Workspace: {workspace}")
    print(f"Manifest: {workspace / 'artifact-manifest.json'}")
    print(f"Artifact Digest (SHA-256): {manifest.artifact_digest_sha256}")

    if manifest.llm_inference:
        meta = manifest.llm_inference
        print(f"Provider: {meta.provider}")
        print(f"Response Model: {meta.response_model_identifier}")
        print(f"Latency: {meta.client_inference_latency_ms} ms")
        if hasattr(meta.response, "input_tokens"):
            print(f"Input Tokens: {meta.response.input_tokens}")
            print(f"Output Tokens: {meta.response.output_tokens}")
            print(f"Total Tokens: {meta.response.total_tokens}")
    print("=" * 60)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run isolated Claude experiment on dynamic C1/C2 project fixtures."
    )
    parser.add_argument(
        "--fixture",
        choices=(
            "task_management",
            "student_management",
            "library_management",
            "inventory_management",
            "gpa",
            "calculator",
        ),
        default="task_management",
        help="Simulated C1/C2 project fixture to test.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run_experiment(args.fixture)))


if __name__ == "__main__":
    main()
