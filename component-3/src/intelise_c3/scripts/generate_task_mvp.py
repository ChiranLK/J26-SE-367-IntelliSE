"""Manual fixed-input experiment for the Task Management generation MVP."""

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
from intelise_c3.llm.ollama import OllamaLLMClient
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService
from intelise_c3.services.stack_selection import StackSelectionService

COMPONENT_ROOT = Path(__file__).resolve().parents[3]
SIMULATED_INPUT = (
    COMPONENT_ROOT
    / "tests"
    / "fixtures"
    / "simulated"
    / "task_management_input_package.json"
)


def build_simulated_request(mode: GenerationMode) -> CodeGenerationRequest:
    """Build the documented simulated pipeline; it is not upstream proof."""
    payload = json.loads(SIMULATED_INPUT.read_text(encoding="utf-8"))
    package = ProvisionalInputPackage.model_validate(payload)
    generation_context = InputValidationService().validate(package)
    design_context = DesignUnderstandingService().build(generation_context)
    evidence = CriterionEvidence(
        reference="SIMULATED-TASK6-MANUAL-EVIDENCE",
        confidence=1.0,
        uncertainty_notes="Manual local MVP experiment only",
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
            approval_reference="SIMULATED-TASK6-MANUAL-APPROVAL",
            approved_by="LOCAL-RESEARCHER-MANUAL-EXPERIMENT",
            acknowledges_provisional_policy=True,
        ),
        mode=mode,
        workspace_name="task-management-manual",
    )


async def run(mode: GenerationMode) -> int:
    settings = Settings()
    request = build_simulated_request(mode)
    client = OllamaLLMClient(settings) if mode is GenerationMode.LOCAL_LLM else None
    service = CodeGenerationService(settings.generated_workspace_root, client)
    try:
        result = await service.generate(request)
    except ApplicationError as exception:
        error = exception.errors[0]
        print(f"Generation failed [{error.code}]: {error.message}")
        return 1

    workspace = settings.generated_workspace_root / Path(
        result.workspace_relative_path
    )
    service_record = next(
        record
        for record in result.manifest.files
        if record.relative_path == "backend/src/services/taskService.js"
    )
    print("Generation completed without executing generated code.")
    print(f"Mode: {result.manifest.generation_mode}")
    print(f"Workspace: {workspace}")
    print(f"Manifest: {workspace / 'artifact-manifest.json'}")
    print(f"Business-logic origin: {service_record.origin.value}")
    print(f"Artifact digest: {result.manifest.artifact_digest_sha256}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the fixed simulated Task Management MVP input."
    )
    parser.add_argument(
        "--mode",
        choices=("local-llm", "template-only"),
        default="local-llm",
    )
    arguments = parser.parse_args()
    mode = (
        GenerationMode.LOCAL_LLM
        if arguments.mode == "local-llm"
        else GenerationMode.TEMPLATE_ONLY
    )
    raise SystemExit(asyncio.run(run(mode)))


if __name__ == "__main__":
    main()
