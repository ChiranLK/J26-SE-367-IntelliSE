"""Run an explicit 10-task RAG ablation with real local Ollama generation.

This script performs 30 model calls and writes only under the ignored runtime
directory. It does not execute generated JavaScript and does not claim C4 test
results. Reported violations come from C3's deterministic structural verifier.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path

from intelise_c3.contracts.generation import GenerationMode
from intelise_c3.contracts.structural_verification import StructuralVerificationRequest
from intelise_c3.core.config import COMPONENT_ROOT, Settings
from intelise_c3.domain.structural_verification import StructuralFindingStatus
from intelise_c3.llm.ollama import OllamaLLMClient
from intelise_c3.rag.runtime import RagRuntime
from intelise_c3.scripts.generate_task_mvp import build_simulated_request
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.structural_verification import StructuralVerificationService
from intelise_c3.traceability.verification import ManifestVerificationService

TASKS = (
    "Create and list records through a repository boundary",
    "Update an existing record and reject an unknown identifier",
    "Delete an existing record and return a consistent not-found error",
    "Validate user input before calling persistence",
    "Keep the controller thin and delegate business rules",
    "Inject repository collaborators so tests can use fakes",
    "Avoid direct database access from request handlers",
    "Preserve stable API error codes and HTTP statuses",
    "Generate secure identifiers without hard-coded secrets",
    "Keep unrelated behavior unchanged while implementing CRUD operations",
)


def _request(task: str, index: int):
    request = build_simulated_request(GenerationMode.LOCAL_LLM)
    design_requirements = tuple(
        requirement.model_copy(
            update={"title": f"{requirement.title}. Ablation task: {task}"}
        )
        for requirement in request.design_context.requirements
    )
    generation_requirements = tuple(
        requirement.model_copy(
            update={"title": f"{requirement.title}. Ablation task: {task}"}
        )
        for requirement in request.generation_context.requirements
    )
    return request.model_copy(
        update={
            "workspace_name": f"task-{index:02d}",
            "design_context": request.design_context.model_copy(
                update={"requirements": design_requirements}
            ),
            "generation_context": request.generation_context.model_copy(
                update={"requirements": generation_requirements}
            ),
        }
    )


async def run() -> dict:
    settings = Settings()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = COMPONENT_ROOT / "runtime" / "rag-ablation" / stamp
    root.mkdir(parents=True, exist_ok=False)
    llm = OllamaLLMClient(settings)
    verifier = StructuralVerificationService(ManifestVerificationService(root))
    conditions = (
        ("RAG_OFF", RagRuntime.disabled()),
        ("FILTER", RagRuntime.from_settings(settings.model_copy(update={"rag_enabled": True, "rag_backend": "filter"}))),
        ("CHROMA", RagRuntime.from_settings(settings.model_copy(update={"rag_enabled": True, "rag_backend": "chroma"}))),
    )
    report = {
        "classification": "C3_RAG_ABLATION_ACTUAL_LOCAL_RUN",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "task_count_per_condition": len(TASKS),
        "conditions": [],
        "limitations": [
            "The ten tasks are controlled Task-MVP prompt variants, not an external benchmark.",
            "Structural violations do not establish semantic correctness or C4 approval.",
        ],
    }
    for condition, runtime in conditions:
        service = CodeGenerationService(root, llm, runtime)
        condition_rows = []
        violation_total = 0
        for index, task in enumerate(TASKS, start=1):
            request = _request(task, index)
            try:
                result = await service.generate(request)
                structural = verifier.verify(
                    StructuralVerificationRequest(
                        manifest=result.manifest,
                        workspace_relative_path=result.workspace_relative_path,
                        design_context=request.design_context,
                    )
                )
                violations = sum(
                    finding.status is StructuralFindingStatus.FAIL
                    for finding in structural.findings
                )
                violation_total += violations
                condition_rows.append(
                    {
                        "task_number": index,
                        "task": task,
                        "generation_run_id": result.manifest.generation_run_id,
                        "architecture_violation_count": violations,
                        "retrieved_rule_ids": sorted(
                            {
                                rule_id
                                for retrieval in result.manifest.run_evidence.rag.retrievals
                                for rule_id in retrieval.retrieved_rule_ids
                            }
                        ),
                    }
                )
            except Exception as exc:  # report the failed observation; never invent a score
                condition_rows.append(
                    {
                        "task_number": index,
                        "task": task,
                        "error_type": type(exc).__name__,
                        "architecture_violation_count": None,
                    }
                )
        report["conditions"].append(
            {
                "condition": condition,
                "architecture_violation_count": violation_total,
                "runs": condition_rows,
            }
        )
    report_path = root / "rag-ablation-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"REPORT_PATH={report_path}")
    return report


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()) is None)
