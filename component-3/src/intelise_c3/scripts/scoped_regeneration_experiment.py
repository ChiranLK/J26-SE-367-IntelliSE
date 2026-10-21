"""Controlled scoped-regeneration experiment on one SIMULATED injected defect.

Evidence classes are kept separate and printed with every result:

* ``--model mock``: a deterministic test double returns a fixed repair. This
  exercises the pipeline only and says nothing about model quality.
* ``--model ollama``: the local ``qwen2.5-coder:3b`` proposes the repair.

In both modes the defect is injected into a fixture baseline and the C4 defect
report is a SIMULATED fixture. No generated JavaScript is executed and no C4
re-test result exists; repair success is therefore never claimed.
"""

import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from intelise_c3.contracts.defect_report import DefectItem, DefectReport
from intelise_c3.contracts.generation import GenerationMode
from intelise_c3.contracts.scoped_regeneration import ScopedRegenerationRequest
from intelise_c3.contracts.traceability import GraphCreateRequest
from intelise_c3.core.config import Settings
from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.generation import GenerationRunResult
from intelise_c3.domain.llm import (
    LLMGenerationParameters,
    LLMInferenceMetadata,
    LLMInferenceRequest,
    LLMInferenceResponse,
    OllamaResponseMetadata,
)
from intelise_c3.domain.scoped_regeneration import ScopedRegenerationResult
from intelise_c3.llm.client import LLMClient
from intelise_c3.llm.ollama import OllamaLLMClient
from intelise_c3.scripts.generate_task_mvp import build_simulated_request
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.scoped_regeneration import ScopedRegenerationService
from intelise_c3.services.traceability import TraceabilityService
from intelise_c3.traceability.builder import TraceabilityGraphBuilder
from intelise_c3.traceability.store import SQLiteTraceabilityStore
from intelise_c3.traceability.verification import ManifestVerificationService

COMPONENT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIRECTORY = COMPONENT_ROOT / "tests" / "fixtures" / "simulated" / "scoped_regeneration"
SERVICE_PATH = "backend/src/services/taskService.js"
PRIMARY_SCENARIO_ID = "SIM-SCN-001-service-update-missing-task"
MOCK_MODEL_LABEL = "SIMULATED-MOCK-MODEL-NOT-OLLAMA"


class SimulatedModelClient:
    """Deterministic test double. It never claims to be a real local model."""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.requests: list[LLMInferenceRequest] = []

    async def generate(self, request: LLMInferenceRequest) -> LLMInferenceResponse:
        self.requests.append(request)
        output = self._outputs.pop(0) if len(self._outputs) > 1 else self._outputs[0]
        return LLMInferenceResponse(
            output_text=output,
            metadata=LLMInferenceMetadata(
                configured_model_identifier=MOCK_MODEL_LABEL,
                response_model_identifier=MOCK_MODEL_LABEL,
                prompt_template_version=request.prompt_template_version,
                generation_parameters=LLMGenerationParameters(
                    temperature=0.0, num_ctx=4096, timeout_seconds=1.0
                ),
                client_inference_latency_ms=0.0,
                response=OllamaResponseMetadata(
                    created_at="SIMULATED", done=True, done_reason="SIMULATED"
                ),
            ),
        )


def fixture_json(name: str) -> Any:
    return json.loads((FIXTURE_DIRECTORY / name).read_text(encoding="utf-8"))


def model_output(path: str, content: str) -> str:
    return json.dumps({"path": path, "content": content})


def load_scenarios() -> dict[str, Any]:
    return fixture_json("c4_defect_scenarios.json")


def build_defective_baseline(
    workspace_root: Path,
) -> tuple[Any, GenerationRunResult]:
    """Create the original run with the SIMULATED injected-defect service module."""
    buggy = (FIXTURE_DIRECTORY / "buggy_task_service.js").read_text(encoding="utf-8")
    request = build_simulated_request(GenerationMode.LOCAL_LLM)
    client = SimulatedModelClient([model_output(SERVICE_PATH, buggy)])
    result = asyncio.run(CodeGenerationService(workspace_root, client).generate(request))
    return request, result


def build_defect_report(
    result: GenerationRunResult,
    defects: list[dict[str, Any]],
    *,
    report_id: str,
    graph_version: int,
) -> DefectReport:
    return DefectReport(
        source_classification="SIMULATED_C4_FIXTURE",
        defect_report_id=report_id,
        reported_at_utc=datetime.now(UTC).isoformat(),
        source_generation_run_id=result.manifest.generation_run_id,
        source_artifact_digest_sha256=result.manifest.artifact_digest_sha256,
        source_graph_version=graph_version,
        defects=tuple(DefectItem.model_validate(item) for item in defects),
    )


def build_traceability(workspace_root: Path, store_path: Path) -> TraceabilityService:
    return TraceabilityService(
        verifier=ManifestVerificationService(workspace_root),
        builder=TraceabilityGraphBuilder(),
        store=SQLiteTraceabilityStore(store_path),
    )


def run_experiment(
    *,
    workspace_root: Path,
    store_path: Path,
    client: LLMClient,
    evidence_class: str,
) -> tuple[ScopedRegenerationResult, GenerationRunResult]:
    design_request, baseline = build_defective_baseline(workspace_root)
    traceability = build_traceability(workspace_root, store_path)
    traceability.create(
        GraphCreateRequest(
            manifest=baseline.manifest,
            workspace_relative_path=baseline.workspace_relative_path,
        )
    )
    scenario = next(
        item for item in load_scenarios()["scenarios"] if item["scenario_id"] == PRIMARY_SCENARIO_ID
    )
    report = build_defect_report(
        baseline, scenario["defects"], report_id="SIM-C4-REPORT-001", graph_version=1
    )
    service = ScopedRegenerationService(
        workspace_root,
        traceability,
        client,
        model_evidence_class=evidence_class,  # type: ignore[arg-type]
    )
    result = asyncio.run(
        service.regenerate(
            ScopedRegenerationRequest(
                defect_report=report,
                manifest=baseline.manifest,
                workspace_relative_path=baseline.workspace_relative_path,
                design_context=design_request.design_context,
            )
        )
    )
    return result, baseline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", choices=("mock", "ollama"), default="mock")
    arguments = parser.parse_args()
    settings = Settings()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    workspace_root = settings.generated_workspace_root / "experiments" / f"scoped-{stamp}"
    store_path = COMPONENT_ROOT / "runtime" / "traceability" / "experiments" / f"{stamp}.sqlite3"

    if arguments.model == "ollama":
        client: LLMClient = OllamaLLMClient(settings)
        evidence_class = "REAL_LOCAL_OLLAMA"
    else:
        repaired = (FIXTURE_DIRECTORY / "repaired_task_service.js").read_text(encoding="utf-8")
        client = SimulatedModelClient([model_output(SERVICE_PATH, repaired)])
        evidence_class = "MOCKED_TEST_DOUBLE"

    try:
        result, baseline = run_experiment(
            workspace_root=workspace_root,
            store_path=store_path,
            client=client,
            evidence_class=evidence_class,
        )
    except ApplicationError as exception:
        error = exception.errors[0]
        print(f"Experiment stopped [{error.code}]: {error.message}")
        raise SystemExit(1) from exception

    source_still_valid = True
    try:
        ManifestVerificationService(workspace_root).verify(
            baseline.manifest, baseline.workspace_relative_path
        )
    except ApplicationError:
        source_still_valid = False

    output_path = workspace_root / "experiment-result.json"
    output_path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    selected = [item.relative_path for item in result.impact_selection.selected_modules]
    print(f"Model evidence class : {result.model_evidence_class}")
    print("Defect input         : SIMULATED_C4_FIXTURE (injected defect, not real C4 output)")
    print(f"Status               : {result.status.value}")
    print(f"Selected modules     : {selected}")
    if result.artifact_versioning and result.preservation and result.graph_versioning:
        versioning = result.artifact_versioning
        print(f"Source run           : {versioning.source_generation_run_id}")
        print(f"New run              : {versioning.new_generation_run_id}")
        print(f"Artifact digest      : {versioning.source_artifact_digest_sha256[:16]}... -> "
              f"{versioning.new_artifact_digest_sha256[:16]}...")
        print(f"Graph version        : {result.graph_versioning.base_graph_version} -> "
              f"{result.graph_versioning.new_graph_version}")
        print(f"Unchanged byte-identical: {result.preservation.all_unselected_files_byte_identical} "
              f"({result.preservation.unchanged_file_count} files)")
        print(f"Collateral edits     : {result.preservation.collateral_edit_count}")
    print(f"Source run untouched : {source_still_valid}")
    if result.c4_retest_handoff:
        print(f"C4 re-test           : {result.c4_retest_handoff.retest_status} (no independent C4 evidence)")
    print("Repair success       : NOT_EVALUATED (requires independent C4 re-testing)")
    print(f"Result file          : {output_path}")


if __name__ == "__main__":
    main()
