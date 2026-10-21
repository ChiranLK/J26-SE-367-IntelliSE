"""OpenRouter trial: let the LLM write a module the templates already produce, then compare.

A trial is an experiment, not a generation path. It never changes the run, the
manifest, the trace graph or the artifact digest; the deterministic template
module stays the accepted artifact. The LLM module goes through the same bounded
gateway (one call per module, minimal context, <=2 attempts, cache, ledger) and
the same static validation as any model output. It is then executed ONLY inside a
disposable Docker container (no network, read-only root, tmpfs only, no mounts,
non-root, capabilities dropped) against the same benchmark cases as the template
module, so the comparison shows behaviour, not appearance.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
import json
import subprocess
from typing import Any
from uuid import uuid4

from fastapi import status

from intelise_c3.contracts.hybrid import HybridInputPackage
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.hybrid.gpa_spec import build_gpa_spec
from intelise_c3.hybrid.gpa_templates import MODULES
from intelise_c3.hybrid.input_contracts import HybridContractValidator
from intelise_c3.hybrid.llm_gateway import (
    PROMPT_VERSION,
    BoundedModuleContext,
    InterfaceMethod,
    OpenRouterModuleGateway,
)
from intelise_c3.hybrid.llm_modules import service_contract_notes
from intelise_c3.hybrid.llm_sandbox import CASES, SANDBOX_IMAGE, run_sandbox, service_spec
from intelise_c3.hybrid.pipeline import EVIDENCE_DIR, PROJECT_DIR, HybridPipeline

TRIAL_CLASSIFICATION = "LLM_TRIAL_NOT_PART_OF_ARTIFACT"
SERVICE_PATH = "backend/src/services/gpaCalculationService.js"
ERRORS_PATH = "backend/src/errors.js"
def _fail(code: str, message: str, status_code: int = status.HTTP_409_CONFLICT) -> ApplicationError:
    return ApplicationError([ErrorDetail(code=code, field="llm_trial", message=message)], status_code=status_code)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class LlmModuleTrial:
    def __init__(self, pipeline: HybridPipeline, *, runner=subprocess.run) -> None:
        self._pipeline = pipeline
        self._run = runner

    # ------------------------------------------------------------------ context
    def _context(self, run_dir, manifest, package: HybridInputPackage) -> tuple[BoundedModuleContext, dict[str, Any]]:
        pipeline = self._pipeline
        validated = HybridContractValidator().validate(package)
        classes = {parsed.name: parsed for parsed in validated.design_context.classes}
        service = classes["GpaCalculationService"]
        module = next(m for m in manifest["modules"] if m["module_id"] == "be.service")
        statements = {r.requirement_id: r for r in package.c1.requirements}
        slices = tuple(
            {"requirement_id": rid, "requirement_version": statements[rid].requirement_version, "statement": statements[rid].statement}
            for rid in module["direct_requirement_ids"]
        )
        methods = [
            InterfaceMethod(m.name, tuple(p.name for p in m.parameters)) for m in service.methods
        ]
        uml_slice = "class GpaCalculationService {\n" + "\n".join(
            f"  +{m.name}({', '.join(f'{p.name}: {p.type_name}' for p in m.parameters)}): {m.return_type or 'void'}" for m in service.methods
        ) + "\n}"
        notes = service_contract_notes(pipeline.kb)
        rag = pipeline._rag("trial.be.service", MODULES["be.service"], applied=True)
        context = BoundedModuleContext(
            module_id="trial.be.service", target_path=SERVICE_PATH, class_name="GpaCalculationService",
            methods=tuple(methods), requirement_slices=slices, uml_slice=uml_slice, uml_version=package.c2.uml_version,
            stack_id=manifest["stack"]["stack_id"], rule_ids=tuple(module["rule_ids"]), kb_digest=pipeline.kb.digest_sha256,
            rule_set_digest=pipeline.rules.digest_sha256, rag_prompt=rag.pop("_prompt"), rag_digest=rag["context_digest_sha256"],
            contract_notes=notes,
        )
        return context, rag

    # ------------------------------------------------------------------ trial
    async def run(self, run_id: str, *, bypass_cache: bool = False) -> dict[str, Any]:
        pipeline = self._pipeline
        run_dir, manifest = pipeline.find_run(run_id)
        problems = pipeline.verify_run_files(run_dir, manifest)
        if problems:
            raise _fail("BASE_RUN_TAMPERED", f"Run {run_id} no longer matches its manifest: {problems[:3]}")
        if not any(m["module_id"] == "be.service" for m in manifest["modules"]):
            raise _fail("TRIAL_MODULE_MISSING", "This run has no be.service module.", status.HTTP_422_UNPROCESSABLE_ENTITY)
        package = HybridInputPackage.model_validate(
            json.loads((run_dir / EVIDENCE_DIR / "input-package.json").read_text(encoding="utf-8")))
        files = pipeline._read_project_files(run_dir, manifest)
        template_source = files[SERVICE_PATH]
        context, rag = self._context(run_dir, manifest, package)
        settings = pipeline.settings
        gateway = OpenRouterModuleGateway(
            pipeline._client(), provider="openrouter", model=settings.openrouter_model,
            cache_dir=settings.hybrid_llm_cache_dir, max_input_tokens=settings.hybrid_llm_max_input_tokens,
        )
        generated = await gateway.generate(context, use_cache=not bypass_cache)
        for entry in generated.ledger:
            entry["module_id"] = context.module_id
            entry["cache_key"] = generated.cache_key
        trial: dict[str, Any] = {
            "trial_id": f"trial-{uuid4().hex[:10]}",
            "classification": TRIAL_CLASSIFICATION,
            "note": "The deterministic template module remains the accepted artifact. This trial never changes the run, manifest, trace graph or artifact digest.",
            "generation_run_id": run_id,
            "artifact_digest_sha256": manifest["artifact_digest_sha256"],
            "module_id": "be.service",
            "provider": "openrouter",
            "requested_model": settings.openrouter_model,
            "prompt_version": PROMPT_VERSION,
            "status": generated.status,
            "reasons": generated.reasons,
            "cache_hit": generated.cache_hit,
            "ledger": generated.ledger,
            "context_summary": {
                "requirement_ids": [r["requirement_id"] for r in context.requirement_slices],
                "uml_classes": ["GpaCalculationService"],
                "rule_ids": list(context.rule_ids),
                "rag_chunks": [h["chunk_id"] for h in rag["hits"]],
                "other_requirements_or_files_sent": 0,
            },
            "template": {"sha256": sha256(template_source.encode("utf-8")).hexdigest(), "lines": template_source.count("\n"), "source": template_source},
            "llm": None,
            "sandbox": {"image": SANDBOX_IMAGE, "network": "none", "root": "read-only", "mounts": "none", "user": "1000:1000"},
            "comparison": None,
            "verdict": None,
            "recorded_at_utc": _now(),
        }
        if generated.content is not None:
            trial["llm"] = {"sha256": sha256(generated.content.encode("utf-8")).hexdigest(), "lines": generated.content.count("\n"), "source": generated.content,
                            "identical_to_template": generated.content.strip() == template_source.strip()}
            gpa_spec = build_gpa_spec(package, HybridContractValidator().validate(package).design_context, pipeline.kb)
            entry = SERVICE_PATH.removeprefix("backend/")
            spec = service_spec(gpa_spec, entry)
            loop = asyncio.get_running_loop()
            llm_run = await loop.run_in_executor(None, run_sandbox, self._run, {entry: generated.content}, spec)
            control = await loop.run_in_executor(
                None, run_sandbox, self._run,
                {ERRORS_PATH.removeprefix("backend/"): files[ERRORS_PATH], entry: template_source}, spec)
            trial["comparison"] = {"llm": llm_run, "template": control, "cases": [c["id"] for c in CASES]}
            if not llm_run["executed"] or not control["executed"]:
                trial["verdict"] = "NOT_EXECUTED: " + (llm_run.get("reason") or control.get("reason"))
            elif control["passed"] != control["total"]:
                trial["verdict"] = "CONTROL_FAILED: the template module failed its own benchmark, so the comparison is not valid."
            elif llm_run["passed"] == llm_run["total"]:
                trial["verdict"] = (f"LLM_MODULE_PASSED_ALL_{llm_run['total']}_BENCHMARK_CASES (trial only; "
                                    "not independent C4 testing and not adopted into the artifact)")
            else:
                failed = [r["id"] for r in llm_run["results"] if not r["passed"]]
                trial["verdict"] = f"LLM_MODULE_FAILED_{len(failed)}_OF_{llm_run['total']}: {', '.join(failed)}"
        else:
            trial["verdict"] = f"NO_MODULE_TO_COMPARE: {generated.status}"
        with (run_dir / EVIDENCE_DIR / "llm-trials.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(trial, sort_keys=True) + "\n")
        return trial


__all__ = ["LlmModuleTrial", "CASES", "TRIAL_CLASSIFICATION", "PROJECT_DIR"]
