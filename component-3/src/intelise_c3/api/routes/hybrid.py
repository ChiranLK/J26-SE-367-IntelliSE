"""Hybrid rule-governed generation routes (KB + rules + templates + RAG + bounded OpenRouter).

Execution is LOCAL_SANDBOX_PREVIEW only. The deployment gate is a contract stub:
CI/CD is DEFERRED_AFTER_PP1 and production deployment is OUT_OF_SCOPE_FOR_PP1.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request, status
from fastapi import Response
from fastapi.responses import PlainTextResponse

from intelise_c3.contracts.hybrid import (
    C4DefectSubmission,
    DeploymentGateRequest,
    HybridGenerationRequest,
    HybridInputPackage,
    HybridLlmTrialRequest,
    HybridPreviewRequest,
    HybridPreviewStopRequest,
    RequirementChangeRequest,
)
from intelise_c3.core.config import COMPONENT_ROOT, Settings
from intelise_c3.core.errors import ApplicationError, ErrorDetail, ErrorResponse
from intelise_c3.hybrid.llm_trial import LlmModuleTrial
from intelise_c3.hybrid.pipeline import PP1_SCOPE, PROJECT_DIR, BackendLlm, HybridPipeline
from intelise_c3.hybrid.preview import EXECUTION_LABEL, KNOWN_GPA_CHECK, HybridPreviewService
from intelise_c3.llm.client import LLMClient

router = APIRouter(prefix="/hybrid", tags=["hybrid-generation"])
FIXTURE_ROOT = COMPONENT_ROOT / "tests" / "fixtures" / "hybrid"
FIXTURES = {
    "gpa-input": ("gpa_input_package.json", "SIMULATED C1/C2 2.0 fixture for the GPA benchmark"),
    "gpa-input-req103-v2": ("gpa_input_package_req103_v2.json", "SIMULATED approved change: REQ-GPA-103 v2 adds a module-code pattern"),
    "gpa-input-req104-v2": ("gpa_input_package_req104_v2.json", "SIMULATED approved change: REQ-GPA-104 v2 adds clearing the calculation history"),
    "gpa-custom-extension": ("gpa_custom_extension_package.json", "SIMULATED design with a custom class no rule covers (LLM path)"),
}
_ERRORS = {
    404: {"model": ErrorResponse, "description": "Run, preview or fixture not found."},
    409: {"model": ErrorResponse, "description": "Contract, staleness, policy or gate conflict."},
    422: {"model": ErrorResponse, "description": "Unsupported design/stack or invalid request."},
    502: {"model": ErrorResponse, "description": "Docker or provider failure."},
    503: {"model": ErrorResponse, "description": "Docker unavailable."},
}


def _openrouter_factory(settings: Settings):
    def factory() -> LLMClient | None:
        # OpenRouter only. Local Ollama is never probed, started or used as a fallback.
        if settings.generation_provider != "openrouter" or not settings.openrouter_experiment_enabled:
            return None
        if not (settings.openrouter_api_key or "").strip():
            return None
        from intelise_c3.llm.openrouter import OpenRouterLLMClient

        bounded = settings.model_copy(update={"openrouter_max_tokens": settings.hybrid_llm_max_output_tokens,
                                             "openrouter_reasoning_effort": settings.hybrid_llm_reasoning_effort})
        return OpenRouterLLMClient(bounded, temperature=0.0)

    return factory


def _teamsoclo_backend(settings: Settings) -> BackendLlm:
    """TeamSocLo (Claude via the experimental gateway) writes backend logic only when the caller opts in."""

    def factory() -> LLMClient | None:
        if not settings.teamsoclo_experiment_enabled or not (settings.teamsoclo_api_key or "").strip():
            return None
        from intelise_c3.llm.teamsoclo import TeamSocLoClaudeLLMClient

        return TeamSocLoClaudeLLMClient(settings)

    def frontend_factory() -> LLMClient | None:
        # UI code is far longer than a service module and this gateway measured ~25 tokens/s: raise the cap and the timeout.
        if not settings.teamsoclo_experiment_enabled or not (settings.teamsoclo_api_key or "").strip():
            return None
        from intelise_c3.llm.teamsoclo import TeamSocLoClaudeLLMClient

        return TeamSocLoClaudeLLMClient(settings.model_copy(update={
            "teamsoclo_max_tokens": settings.hybrid_llm_frontend_max_output_tokens,
            "teamsoclo_timeout_seconds": settings.hybrid_llm_frontend_timeout_seconds,
        }))

    return BackendLlm(provider="teamsoclo", model=settings.teamsoclo_model, client_factory=factory,
                      frontend_client_factory=frontend_factory)


def pipeline_for(request: Request) -> HybridPipeline:
    state = request.app.state
    if getattr(state, "hybrid_pipeline", None) is None:
        state.hybrid_pipeline = HybridPipeline(
            state.settings, llm_client_factory=_openrouter_factory(state.settings),
            backend_llm=_teamsoclo_backend(state.settings))
    return state.hybrid_pipeline


def preview_for(request: Request) -> HybridPreviewService:
    state = request.app.state
    if getattr(state, "hybrid_preview", None) is None:
        state.hybrid_preview = HybridPreviewService(pipeline_for(request))
    return state.hybrid_preview


@router.get("/overview", summary="Knowledge Base, rule set, policy, provider and PP1 scope")
def overview(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    pipeline = pipeline_for(request)
    return {
        "pp1_scope": PP1_SCOPE,
        "execution_label": EXECUTION_LABEL,
        "knowledge_base": pipeline.knowledge_summary(),
        "rule_set": pipeline.rules_summary(),
        "policy_acceptance_template": pipeline.policy_acceptance_template(),
        "rag": {"backend": pipeline.rag_backend, "rule_corpus_sha256": pipeline.rag_corpus,
                "limits": {"top_k": "3-5", "max_context_tokens": 2000}},
        "llm": {
            "provider": "openrouter",
            "generation_provider_setting": settings.generation_provider,
            "experiment_enabled": settings.openrouter_experiment_enabled,
            "api_key_configured": bool((settings.openrouter_api_key or "").strip()),
            "model": settings.openrouter_model,
            "max_input_tokens": settings.hybrid_llm_max_input_tokens,
            "max_output_tokens": settings.hybrid_llm_max_output_tokens,
            "max_attempts": 2,
            "ollama": "NOT_USED",
            "teamsoclo": {
                "role": "LLM backend logic (service + validation) and/or LLM frontend (UI files) when the caller opts in",
                "experiment_enabled": settings.teamsoclo_experiment_enabled,
                "api_key_configured": bool((settings.teamsoclo_api_key or "").strip()),
                "model": settings.teamsoclo_model,
            },
        },
        "fixtures": {key: label for key, (_, label) in FIXTURES.items()},
        "known_gpa_check": KNOWN_GPA_CHECK,
    }


@router.get("/fixtures/{fixture_id}", responses=_ERRORS, summary="Load a SIMULATED hybrid demo fixture")
def fixture(fixture_id: str) -> dict[str, Any]:
    if fixture_id not in FIXTURES:
        raise ApplicationError([ErrorDetail(code="FIXTURE_NOT_FOUND", field="fixture_id", message=f"Unknown fixture {fixture_id}.")],
                               status_code=status.HTTP_404_NOT_FOUND)
    name, label = FIXTURES[fixture_id]
    return {"fixture_id": fixture_id, "classification": "SIMULATED_FIXTURE", "label": label,
            "payload": json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))}


@router.post("/contracts/validate", summary="Validate a 2.0 C1/C2 package without generating")
def validate_contract(package: HybridInputPackage, request: Request) -> dict[str, Any]:
    return pipeline_for(request).contract_report(package)


@router.post("/runs", status_code=status.HTTP_201_CREATED, responses=_ERRORS, summary="Generate a project through the hybrid pipeline")
async def create_run(payload: HybridGenerationRequest, request: Request) -> dict[str, Any]:
    return await pipeline_for(request).generate(payload)


@router.get("/runs", summary="List hybrid runs, newest first")
def list_runs(request: Request) -> list[dict[str, Any]]:
    return pipeline_for(request).list_runs()


@router.get("/runs/{run_id}", responses=_ERRORS, summary="Manifest plus verification, gate and preview evidence")
def get_run(run_id: str, request: Request) -> dict[str, Any]:
    return pipeline_for(request).run_report(run_id)


@router.get("/runs/{run_id}/audit", response_class=PlainTextResponse, responses=_ERRORS, summary="Audit report (Markdown)")
def get_audit(run_id: str, request: Request) -> str:
    return pipeline_for(request).audit_markdown(run_id)


@router.get("/runs/{run_id}/archive", responses={**_ERRORS, 200: {"content": {"application/zip": {}}, "description": "Project zip."}},
            summary="Download the generated project as a zip after every file was re-hashed")
def get_archive(run_id: str, request: Request) -> Response:
    name, data = pipeline_for(request).archive_zip(run_id)
    return Response(content=data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _open_in_file_manager(path: Path) -> None:
    if os.name != "nt":
        raise ApplicationError(
            [ErrorDetail(code="OPEN_FOLDER_UNSUPPORTED", field="platform",
                         message="Opening a folder from the dashboard only works on Windows. Open the path shown on the page in your file manager.")],
            status_code=status.HTTP_501_NOT_IMPLEMENTED)
    subprocess.Popen(["explorer", str(path)])


@router.get("/runs/{run_id}/location", responses=_ERRORS, summary="Where the generated project folder is on this computer")
def get_location(run_id: str, request: Request) -> dict[str, Any]:
    return {"run_id": run_id, "path": str(pipeline_for(request).project_dir(run_id))}


@router.post("/runs/{run_id}/open-folder", responses=_ERRORS, summary="Open the generated project folder in the file manager (Windows)")
def open_folder(run_id: str, request: Request) -> dict[str, Any]:
    path = pipeline_for(request).project_dir(run_id)
    _open_in_file_manager(path)
    return {"run_id": run_id, "path": str(path), "opened": True}


@router.get("/runs/{run_id}/file", responses=_ERRORS, summary="Read one generated file after hash verification")
def get_file(run_id: str, request: Request, path: str = Query(min_length=1, max_length=300)) -> dict[str, Any]:
    pipeline = pipeline_for(request)
    run_dir, manifest = pipeline.find_run(run_id)
    record = next((r for r in manifest["files"] if r["path"] == path), None)
    if record is None:
        raise ApplicationError([ErrorDetail(code="FILE_NOT_IN_MANIFEST", field="path", message="Path is not a generated file of this run.")],
                               status_code=status.HTTP_404_NOT_FOUND)
    content = (run_dir / PROJECT_DIR / record["path"]).read_bytes().decode("utf-8")
    from hashlib import sha256

    verified = sha256(content.encode("utf-8")).hexdigest() == record["sha256"]
    return {"path": path, "sha256": record["sha256"], "verified": verified, "module_id": record["module_id"],
            "content": content if verified else None}


@router.post("/regenerations/requirement-change", status_code=status.HTTP_201_CREATED, responses=_ERRORS,
             summary="Scoped regeneration for an approved requirement/design change")
async def requirement_change(payload: RequirementChangeRequest, request: Request) -> dict[str, Any]:
    return await pipeline_for(request).requirement_change(payload)


@router.post("/runs/{run_id}/simulated-defect-injection", status_code=status.HTTP_201_CREATED, responses=_ERRORS,
             summary="SIMULATED: derive a run with an injected rounding defect (demo only)")
def inject_defect(run_id: str, request: Request) -> dict[str, Any]:
    return pipeline_for(request).inject_defect_for_demo(run_id)


@router.get("/runs/{run_id}/simulated-c4-defect", responses=_ERRORS, summary="SIMULATED C4 defect fixture bound to this run")
def simulated_defect(run_id: str, request: Request) -> dict[str, Any]:
    return pipeline_for(request).simulated_defect(run_id)


@router.get("/runs/{run_id}/simulated-c4-readiness", responses=_ERRORS, summary="SIMULATED C4 readiness fixture bound to this run")
def simulated_readiness(run_id: str, request: Request) -> dict[str, Any]:
    return pipeline_for(request).simulated_readiness(run_id)


@router.post("/llm-trial", responses=_ERRORS,
             summary="TRIAL: OpenRouter writes one template-produced module; compared in a Docker sandbox, artifact untouched")
async def llm_trial(payload: HybridLlmTrialRequest, request: Request) -> dict[str, Any]:
    return await LlmModuleTrial(pipeline_for(request)).run(payload.generation_run_id, bypass_cache=payload.bypass_cache)


@router.post("/c4/defects", status_code=status.HTTP_201_CREATED, responses=_ERRORS, summary="C4 defect intake -> scoped regeneration")
async def c4_defect(payload: C4DefectSubmission, request: Request) -> dict[str, Any]:
    return await pipeline_for(request).c4_defect(payload)


@router.post("/deployment-gate", responses=_ERRORS, summary="Exact-artifact gate decision (contract stub; nothing is deployed)")
def deployment_gate(payload: DeploymentGateRequest, request: Request) -> dict[str, Any]:
    return pipeline_for(request).deployment_gate(payload)


@router.get("/projects/{project_id}/trace", responses=_ERRORS, summary="Living traceability graph, coverage and versions")
def trace(project_id: str, request: Request, version: int | None = Query(default=None, ge=1)) -> dict[str, Any]:
    return pipeline_for(request).trace(project_id, version)


@router.get("/preview", summary="Docker availability and running LOCAL_SANDBOX_PREVIEW sessions")
def list_previews(request: Request) -> dict[str, Any]:
    service = preview_for(request)
    availability = service.docker_available()
    return {"execution_label": EXECUTION_LABEL, "docker": availability,
            "previews": service.list() if availability["available"] else []}


@router.post("/preview/start", responses=_ERRORS, summary="Build and start a disposable preview; URLs only after health checks")
def start_preview(payload: HybridPreviewRequest, request: Request) -> dict[str, Any]:
    return preview_for(request).start(payload.generation_run_id)


@router.post("/preview/stop", responses=_ERRORS, summary="Stop and remove a preview's containers and networks")
def stop_preview(payload: HybridPreviewStopRequest, request: Request) -> dict[str, Any]:
    return preview_for(request).stop(payload.preview_id)


@router.get("/preview/{preview_id}", responses=_ERRORS, summary="Preview status and live health")
def preview_status(preview_id: str, request: Request) -> dict[str, Any]:
    return preview_for(request).health(preview_id)


@router.post("/preview/{preview_id}/gpa-check", responses=_ERRORS, summary="Run the known GPA calculation against the preview API")
def preview_gpa_check(preview_id: str, request: Request) -> dict[str, Any]:
    return preview_for(request).gpa_check(preview_id)
